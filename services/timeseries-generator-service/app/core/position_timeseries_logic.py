# services/timeseries-generator-service/app/consumers/position_timeseries_consumer.py
import logging
import json
import asyncio
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from tenacity import retry, stop_after_attempt, wait_fixed, before_log, retry_if_exception_type
from confluent_kafka import Message
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import func
from datetime import timedelta, date

from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.events import DailyPositionSnapshotPersistedEvent
from portfolio_common.db import get_async_db_session
from portfolio_common.database_models import DailyPositionSnapshot, PositionHistory, PortfolioAggregationJob, PositionTimeseries

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
    Consumes daily position snapshot events, generates the corresponding daily
    position time series record, and creates an aggregation job.
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

                    # Create an aggregation job. This is now this consumer's primary output.
                    job_stmt = pg_insert(PortfolioAggregationJob).values(
                        portfolio_id=event.portfolio_id,
                        aggregation_date=event.date,
                        status='PENDING',
                        correlation_id=correlation_id
                    ).on_conflict_do_update(
                        index_elements=['portfolio_id', 'aggregation_date'],
                        set_={'status': 'PENDING', 'updated_at': func.now()}
                    )
                    await db.execute(job_stmt)
                    logger.info(f"Successfully staged aggregation job for portfolio {event.portfolio_id} on {event.date}")

                    # --- Roll-forward for all open positions on this date ---
                    await self.roll_forward_open_positions(event.portfolio_id, event.date, db)
                    
        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"Message validation failed: {e}. Sending to DLQ.", exc_info=True)
            await self._send_to_dlq_async(msg, e)
        except (InstrumentNotFoundError, PreviousTimeseriesNotFoundError, IntegrityError) as e:
            logger.warning(f"A recoverable error occurred: {e}. Retrying...")
            raise
        except Exception as e:
            logger.error(f"Unexpected error processing message: {e}", exc_info=True)
            await self._send_to_dlq_async(msg, e)

    async def roll_forward_open_positions(self, portfolio_id: str, a_date: date, db):
        """
        For all positions open on previous day, create today's position_timeseries using previous EOD.
        Only creates a new timeseries if one doesn't already exist for this day/security.
        """
        repo = TimeseriesRepository(db)
        prev_date = a_date - timedelta(days=1)
        open_security_ids = await repo.get_all_open_positions_as_of(portfolio_id, prev_date)
        # Exclude securities already processed for today (e.g., with a new transaction or snapshot)
        existing_ts = await repo.get_all_position_timeseries_for_date(portfolio_id, a_date)
        already_done = {ts.security_id for ts in existing_ts}
        for security_id in open_security_ids:
            if security_id in already_done:
                continue
            prev_ts = await repo.get_last_position_timeseries_before(portfolio_id, security_id, a_date)
            if not prev_ts:
                continue
            # Roll forward values; consider updating with latest market price if desired
            new_ts = PositionTimeseries(
                portfolio_id=portfolio_id,
                security_id=security_id,
                date=a_date,
                bod_market_value=prev_ts.eod_market_value,
                bod_cashflow=0,
                eod_cashflow=0,
                eod_market_value=prev_ts.eod_market_value,  # (Or, recalculate with new price)
                fees=0,
                quantity=prev_ts.quantity,
                cost=prev_ts.cost
            )
            await repo.upsert_position_timeseries(new_ts)
