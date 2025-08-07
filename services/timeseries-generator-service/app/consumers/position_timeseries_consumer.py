# services/timeseries-generator-service/app/consumers/position_timeseries_consumer.py
import logging
import json
import asyncio
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from tenacity import retry, stop_after_attempt, wait_fixed, before_log, retry_if_exception_type
from confluent_kafka import Message
from sqlalchemy.dialects.postgresql import insert as pg_insert

from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.events import DailyPositionSnapshotPersistedEvent, PositionTimeseriesGeneratedEvent
from portfolio_common.db import get_async_db_session
from portfolio_common.database_models import DailyPositionSnapshot, PositionHistory, PortfolioAggregationJob
from portfolio_common.config import KAFKA_POSITION_TIMESERIES_GENERATED_TOPIC

from ..core.position_timeseries_logic import PositionTimeseriesLogic
from ..repositories.timeseries_repository import TimeseriesRepository

logger = logging.getLogger(__name__)

class InstrumentNotFoundError(Exception):
    """Custom exception to signal that a required instrument is not yet persisted."""
    pass

class PreviousTimeseriesNotFoundError(Exception):
    """Custom exception to signal that the previous day's time series record is not yet persisted."""
    pass

class PositionTimeseriesConsumer(BaseConsumer):
    """
    Consumes daily position snapshot events and generates the corresponding daily
    position time series record.
    """
    async def process_message(self, msg: Message):
        """Wrapper to call the retryable logic."""
        retry_config = retry(
            wait=wait_fixed(3),
            stop=stop_after_attempt(5),
            before=before_log(logger, logging.INFO),
            retry=retry_if_exception_type((IntegrityError, InstrumentNotFoundError, PreviousTimeseriesNotFoundError))
        )
        retryable_process = retry_config(self._process_message_with_retry)
        
        try:
            await retryable_process(msg)
        except Exception as e:
            logger.error(f"Fatal error after all retries for message {msg.topic()}-{msg.partition()}-{msg.offset()}. Sending to DLQ.", exc_info=True)
            await self._send_to_dlq_async(msg, e)

    async def _process_message_with_retry(self, msg: Message):
        try:
            event_data = json.loads(msg.value().decode('utf-8'))
            event = DailyPositionSnapshotPersistedEvent.model_validate(event_data)
            correlation_id = correlation_id_var.get() 

            logger.info(f"Processing position snapshot for {event.security_id} on {event.date}")

            async for db in get_async_db_session():
                async with db.begin():
                    repo = TimeseriesRepository(db)
                    
                    instrument = await repo.get_instrument(event.security_id)
                    if not instrument:
                        raise InstrumentNotFoundError(f"Instrument '{event.security_id}' not found. Will retry.")

                    current_snapshot = await db.get(DailyPositionSnapshot, event.id)
                    if not current_snapshot:
                        logger.warning(f"DailyPositionSnapshot record with id {event.id} not found. Skipping.")
                        return

                    previous_timeseries = await repo.get_last_position_timeseries_before(
                        portfolio_id=event.portfolio_id,
                        security_id=event.security_id,
                        a_date=event.date
                    )

                    if previous_timeseries is None:
                        is_truly_first = await repo.is_first_position(
                            portfolio_id=event.portfolio_id,
                            security_id=event.security_id,
                            position_date=event.date
                        )
    
                        if not is_truly_first:
                            raise PreviousTimeseriesNotFoundError(
                                f"Previous day's timeseries for {event.security_id} not found for date {event.date}, but history exists. Retrying."
                            )
                    
                    cashflows = await repo.get_all_cashflows_for_security_date(
                        event.portfolio_id, event.security_id, event.date
                    )
                    
                    bod_cashflow = sum(cf.amount for cf in cashflows if cf.timing == 'BOD')
                    eod_cashflow = sum(cf.amount for cf in cashflows if cf.timing == 'EOD')

                    new_timeseries_record = PositionTimeseriesLogic.calculate_daily_record(
                        current_snapshot=current_snapshot,
                        previous_timeseries=previous_timeseries,
                        bod_cashflow=bod_cashflow,
                        eod_cashflow=eod_cashflow
                    )
                    
                    await repo.upsert_position_timeseries(new_timeseries_record)

                    # --- NEW LOGIC: Create an aggregation job ---
                    # Idempotently create a job to signify this portfolio-date pair needs aggregation.
                    job_stmt = pg_insert(PortfolioAggregationJob).values(
                        portfolio_id=event.portfolio_id,
                        aggregation_date=event.date,
                        status='PENDING',
                        correlation_id=correlation_id
                    ).on_conflict_do_update(
                        index_elements=['portfolio_id', 'aggregation_date'],
                        set_={'status': 'PENDING', 'updated_at': 'now()'}
                    )
                    await db.execute(job_stmt)
                    logger.info(f"Successfully staged aggregation job for portfolio {event.portfolio_id} on {event.date}")
                    # --- END NEW LOGIC ---

                    if self._producer:
                        completion_event = PositionTimeseriesGeneratedEvent.model_validate(new_timeseries_record)
                        headers = [('correlation_id', correlation_id.encode('utf-8'))] if correlation_id else None
                        
                        self._producer.publish_message(
                            topic=KAFKA_POSITION_TIMESERIES_GENERATED_TOPIC,
                            key=completion_event.portfolio_id,
                            value=completion_event.model_dump(mode='json'),
                            headers=headers
                        )
                        self._producer.flush(timeout=5)

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"Message validation failed: {e}. Sending to DLQ.", exc_info=True)
            await self._send_to_dlq_async(msg, e)
        except (InstrumentNotFoundError, PreviousTimeseriesNotFoundError, IntegrityError) as e:
            logger.warning(f"A recoverable error occurred: {e}. Retrying...")
            raise
        except Exception as e:
            logger.error(f"Unexpected error processing message: {e}", exc_info=True)
            await self._send_to_dlq_async(msg, e)