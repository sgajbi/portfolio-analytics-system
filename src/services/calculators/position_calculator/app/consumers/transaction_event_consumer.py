# services/calculators/position_calculator/app/consumers/transaction_event_consumer.py
import logging
import json
from pydantic import ValidationError
from confluent_kafka import Message
from sqlalchemy.exc import DBAPIError, IntegrityError
from tenacity import retry, stop_after_attempt, wait_fixed, before_log, retry_if_exception_type

from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.events import TransactionEvent, PositionHistoryPersistedEvent
from portfolio_common.db import get_async_db_session
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.outbox_repository import OutboxRepository
from portfolio_common.config import KAFKA_POSITION_HISTORY_PERSISTED_TOPIC

from ..repositories.position_repository import PositionRepository
from ..core.position_logic import PositionCalculator

logger = logging.getLogger(__name__)

SERVICE_NAME = "position-calculator"

class TransactionEventConsumer(BaseConsumer):
    """
    Consumes processed transaction completion events (payload is a TransactionEvent),
    recalculates positions using PositionCalculator, persists, and emits completion.
    """

    @retry(
        wait=wait_fixed(2),
        stop=stop_after_attempt(3),
        before=before_log(logger, logging.INFO),
        retry=retry_if_exception_type((DBAPIError, IntegrityError)),
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
                tx = await db.begin()
                try:
                    idempotency_repo = IdempotencyRepository(db)
                    if await idempotency_repo.is_event_processed(event_id, SERVICE_NAME):
                        logger.warning("Event already processed. Skipping.")
                        await tx.rollback()
                        return

                    repo = PositionRepository(db)
                    # Recalculate & stage all affected position history rows
                    new_positions = await PositionCalculator.calculate(event, db, repo=repo)

                    # CORRECTED: Instantiate OutboxRepository with the db session
                    outbox_repo = OutboxRepository(db)
                    
                    # Emit an event for each position record persisted
                    for record in new_positions:
                        completion_event = PositionHistoryPersistedEvent.model_validate(record)

                        # CORRECTED: Call the method on the instantiated object
                        await outbox_repo.create_outbox_event(
                            aggregate_type='PositionHistory',
                            aggregate_id=completion_event.portfolio_id,
                            event_type='PositionHistoryPersisted',
                            topic=KAFKA_POSITION_HISTORY_PERSISTED_TOPIC,
                            payload=completion_event.model_dump(mode="json"),
                            correlation_id=correlation_id
                        )

                    await idempotency_repo.mark_event_processed(
                        event_id, event.portfolio_id, SERVICE_NAME, correlation_id
                    )
                    await db.commit()

                except Exception:
                    await tx.rollback()
                    raise

        except (json.JSONDecodeError, ValidationError):
            logger.error("Invalid processed transaction event; sending to DLQ.", exc_info=True)
            await self._send_to_dlq_async(msg, ValueError("invalid payload"))
        except (DBAPIError, IntegrityError):
            logger.warning("DB error; will retry...", exc_info=False)
            raise
        except Exception as e:
            logger.error("Unexpected error in position calculator; sending to DLQ.", exc_info=True)
            await self._send_to_dlq_async(msg, e)