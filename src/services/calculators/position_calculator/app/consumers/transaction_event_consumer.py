# src/services/calculators/position_calculator/app/consumers/transaction_event_consumer.py
import logging
import json
from datetime import date, timedelta
from pydantic import ValidationError
from confluent_kafka import Message
from sqlalchemy.exc import DBAPIError, IntegrityError
from tenacity import retry, stop_after_attempt, wait_fixed, before_log, retry_if_exception_type

from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.events import TransactionEvent
from portfolio_common.db import get_async_db_session
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.recalculation_job_repository import RecalculationJobRepository
from portfolio_common.database_models import DailyPositionSnapshot

from ..repositories.position_repository import PositionRepository
from ..core.position_logic import PositionCalculator

logger = logging.getLogger(__name__)

SERVICE_NAME = "position-calculator"

class RecalculationInProgressError(Exception):
    """Custom retryable exception when a live transaction conflicts with a historical recalculation."""
    pass

class TransactionEventConsumer(BaseConsumer):
    """
    Consumes processed transaction events, recalculates position history,
    respects recalculation locks, and triggers new recalculation jobs for backdated transactions.
    """
    @retry(
        wait=wait_fixed(5), # Wait longer for retryable errors like the lock
        stop=stop_after_attempt(12),
        before=before_log(logger, logging.INFO),
        retry=retry_if_exception_type((DBAPIError, IntegrityError, RecalculationInProgressError)),
        reraise=True
    )
    async def process_message(self, msg: Message):
        key = msg.key().decode('utf-8') if msg.key() else "NoKey"
        value = msg.value().decode('utf-8')
        event_id = f"{msg.topic()}-{msg.partition()}-{msg.offset()}"
        correlation_id = correlation_id_var.get()

        try:
            data = json.loads(value)
            event = TransactionEvent.model_validate(data)

            async for db in get_async_db_session():
                # FIX: Use 'async with' for correct transaction management
                async with db.begin():
                    idempotency_repo = IdempotencyRepository(db)
                    if await idempotency_repo.is_event_processed(event_id, SERVICE_NAME):
                        logger.warning("Event already processed. Skipping.")
                        return

                    repo = PositionRepository(db)
                    recalc_job_repo = RecalculationJobRepository(db)

                    # --- NEW: Concurrency Lock Check ---
                    if await recalc_job_repo.is_job_processing(event.portfolio_id, event.security_id):
                        raise RecalculationInProgressError(
                            f"Recalculation job is active for {event.portfolio_id}/{event.security_id}. Requeuing message."
                        )
                    
                    new_positions = await PositionCalculator.calculate(event, db, repo=repo)
                    
                    # --- NEW: Backdated Trigger Logic ---
                    latest_business_date = await repo.get_latest_business_date()
                    is_backdated = latest_business_date and event.transaction_date.date() < latest_business_date

                    if is_backdated:
                        logger.info(f"Backdated transaction {event.transaction_id} detected. Staging recalculation job.")
                        await recalc_job_repo.upsert_job(
                            portfolio_id=event.portfolio_id,
                            security_id=event.security_id,
                            from_date=event.transaction_date.date(),
                            correlation_id=correlation_id
                        )

                    await idempotency_repo.mark_event_processed(
                        event_id, event.portfolio_id, SERVICE_NAME, correlation_id
                    )

        except (json.JSONDecodeError, ValidationError):
            logger.error("Invalid processed transaction event; sending to DLQ.", exc_info=True)
            await self._send_to_dlq_async(msg, ValueError("invalid payload"))
        except (DBAPIError, IntegrityError, RecalculationInProgressError):
            logger.warning("DB error or active recalculation lock; will retry...", exc_info=False)
            raise
        except Exception as e:
            logger.error("Unexpected error in position calculator; sending to DLQ.", exc_info=True)
            await self._send_to_dlq_async(msg, e)