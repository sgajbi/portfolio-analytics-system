# src/services/timeseries_generator_service/app/consumers/position_timeseries_consumer.py
import logging
import json
import asyncio
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from tenacity import retry, stop_after_attempt, wait_fixed, before_log, retry_if_exception_type
from confluent_kafka import Message
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import func
from datetime import date, timedelta
from decimal import Decimal

from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.events import DailyPositionSnapshotPersistedEvent
from portfolio_common.db import get_async_db_session
from portfolio_common.database_models import DailyPositionSnapshot, PortfolioAggregationJob, Instrument, PositionState
from portfolio_common.reprocessing import EpochFencer

from ..core.position_timeseries_logic import PositionTimeseriesLogic
from ..repositories.timeseries_repository import TimeseriesRepository

logger = logging.getLogger(__name__)

SERVICE_NAME = "timeseries-generator"

class InstrumentNotFoundError(Exception):
    pass

class PreviousTimeseriesNotFoundError(Exception):
    pass

class PositionTimeseriesConsumer(BaseConsumer):
    async def process_message(self, msg: Message):
        retry_config = retry(
            wait=wait_fixed(3),
            stop=stop_after_attempt(15),
            before=before_log(logger, logging.INFO),
            retry=retry_if_exception_type((IntegrityError, InstrumentNotFoundError))
        )
        retryable_process = retry_config(self._process_message_with_retry)
        try:
            await retryable_process(msg)
        except Exception as e:
            logger.error(f"Fatal error after all retries for message {msg.topic()}-{msg.partition()}-{msg.offset()}. Sending to DLQ.", exc_info=True)
            await self._send_to_dlq_async(msg, e)

    async def _stage_aggregation_job(self, db_session, portfolio_id: str, a_date: date, correlation_id: str):
        """Helper to idempotently create or reset an aggregation job."""
        job_stmt = pg_insert(PortfolioAggregationJob).values(
            portfolio_id=portfolio_id,
            aggregation_date=a_date,
            status='PENDING',
            correlation_id=correlation_id
        ).on_conflict_do_update(
            index_elements=['portfolio_id', 'aggregation_date'],
            set_={'status': 'PENDING', 'updated_at': func.now()}
        )
        await db_session.execute(job_stmt)
        logger.info(f"Successfully staged aggregation job for portfolio {portfolio_id} on {a_date}")

    async def _process_message_with_retry(self, msg: Message):
        try:
            event_data = json.loads(msg.value().decode('utf-8'))
            event = DailyPositionSnapshotPersistedEvent.model_validate(event_data)
            correlation_id = correlation_id_var.get() 

            logger.info(f"Processing position snapshot for {event.security_id} on {event.date} for epoch {event.epoch}")

            async for db in get_async_db_session():
                async with db.begin():
                    repo = TimeseriesRepository(db)
                    
                    # --- REFACTORED: Use EpochFencer ---
                    fencer = EpochFencer(db, service_name=SERVICE_NAME)
                    if not await fencer.check(event):
                        return # Acknowledge message without processing
                    # --- END REFACTOR ---

                    instrument = await repo.get_instrument(event.security_id)
                    if not instrument:
                        raise InstrumentNotFoundError(f"Instrument '{event.security_id}' not found. Will retry.")

                    current_snapshot = await db.get(DailyPositionSnapshot, event.id)
                    if not current_snapshot:
                        logger.warning(f"DailyPositionSnapshot record with id {event.id} not found. Skipping.")
                        return

                    previous_snapshot = await repo.get_last_snapshot_before(
                        portfolio_id=event.portfolio_id,
                        security_id=event.security_id,
                        a_date=event.date,
                        epoch=event.epoch
                    )
                    
                    cashflows = await repo.get_all_cashflows_for_security_date(
                        event.portfolio_id, event.security_id, event.date
                    )
                    
                    new_timeseries_record = PositionTimeseriesLogic.calculate_daily_record(
                        current_snapshot=current_snapshot,
                        previous_snapshot=previous_snapshot,
                        cashflows=cashflows,
                        epoch=event.epoch
                    )
                    
                    await repo.upsert_position_timeseries(new_timeseries_record)
                    await self._stage_aggregation_job(db, event.portfolio_id, event.date, correlation_id)
            
        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"Message validation failed: {e}. Sending to DLQ.", exc_info=True)
            await self._send_to_dlq_async(msg, e)
        except (InstrumentNotFoundError, IntegrityError) as e:
            logger.warning(f"A recoverable error occurred: {e}. Retrying...")
            raise
        except Exception as e:
            logger.error(f"Unexpected error processing message: {e}", exc_info=True)
            await self._send_to_dlq_async(msg, e)