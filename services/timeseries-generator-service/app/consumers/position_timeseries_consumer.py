import logging
import json
import asyncio
from pydantic import ValidationError
from decimal import Decimal
from datetime import date, timedelta

from confluent_kafka import Message
from sqlalchemy.exc import IntegrityError
from tenacity import retry, stop_after_attempt, wait_fixed, before_log

from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.events import DailyPositionSnapshotPersistedEvent, PositionTimeseriesGeneratedEvent
from portfolio_common.db import get_db_session
from portfolio_common.database_models import DailyPositionSnapshot, Cashflow
from portfolio_common.config import KAFKA_POSITION_TIMESERIES_GENERATED_TOPIC

from ..core.position_timeseries_logic import PositionTimeseriesLogic
from ..repositories.timeseries_repository import TimeseriesRepository

logger = logging.getLogger(__name__)

class PositionTimeseriesConsumer(BaseConsumer):
    """
    Consumes daily position snapshot events and generates the corresponding daily
    position time series record.
    """
    def process_message(self, msg: Message, loop: asyncio.AbstractEventLoop):
        """Wrapper to call the retryable logic."""
        self._process_message_with_retry(msg, loop)

    @retry(
        wait=wait_fixed(3),
        stop=stop_after_attempt(5),
        before=before_log(logger, logging.INFO)
    )
    def _process_message_with_retry(self, msg: Message, loop: asyncio.AbstractEventLoop):
        try:
            event_data = json.loads(msg.value().decode('utf-8'))
            event = DailyPositionSnapshotPersistedEvent.model_validate(event_data)
            correlation_id = correlation_id_var.get() 

            logger.info(f"Processing position snapshot for {event.security_id} on {event.date}")

            with next(get_db_session()) as db:
                with db.begin():
                    repo = TimeseriesRepository(db)

                    current_snapshot = db.get(DailyPositionSnapshot, event.id)
                    if not current_snapshot:
                        logger.warning(f"DailyPositionSnapshot record with id {event.id} not found. Skipping.")
                        return

                    previous_timeseries = repo.get_last_position_timeseries_before(
                        portfolio_id=event.portfolio_id,
                        security_id=event.security_id,
                        a_date=event.date
                    )

                    cashflows = db.query(Cashflow).filter(
                        Cashflow.portfolio_id == event.portfolio_id,
                        Cashflow.security_id == event.security_id,
                        Cashflow.cashflow_date == event.date
                    ).all()

                    bod_cashflow = sum(cf.amount for cf in cashflows if cf.timing == 'BOD')
                    eod_cashflow = sum(cf.amount for cf in cashflows if cf.timing == 'EOD')

                    new_timeseries_record = PositionTimeseriesLogic.calculate_daily_record(
                        current_snapshot=current_snapshot,
                        previous_timeseries=previous_timeseries,
                        bod_cashflow=bod_cashflow,
                        eod_cashflow=eod_cashflow
                    )
                    
                    repo.upsert_position_timeseries(new_timeseries_record)

                if self._producer:
                    completion_event = PositionTimeseriesGeneratedEvent.model_validate(new_timeseries_record)
                    headers = [('correlation_id', correlation_id.encode('utf-8'))] if correlation_id else None
                    
                    self._producer.publish_message(
                        topic=KAFKA_POSITION_TIMESERIES_GENERATED_TOPIC,
                        key=f"{completion_event.portfolio_id}:{completion_event.security_id}",
                        value=completion_event.model_dump(mode='json'),
                        headers=headers
                    )
                    self._producer.flush(timeout=5)

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"Message validation failed: {e}. Sending to DLQ.", exc_info=True)
            self._send_to_dlq_sync(msg, e, loop)
        except IntegrityError as e:
            logger.warning(f"Caught IntegrityError (likely a race condition). Retrying...", exc_info=True)
            raise # Re-raise to trigger tenacity retry
        except Exception as e:
            logger.error(f"Unexpected error processing message: {e}", exc_info=True)
            self._send_to_dlq_sync(msg, e, loop)