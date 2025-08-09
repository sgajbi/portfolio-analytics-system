# services/calculators/position_calculator/app/consumers/transaction_event_consumer.py
import logging
import json
from pydantic import ValidationError
from confluent_kafka import Message
from sqlalchemy.exc import DBAPIError, IntegrityError
from tenacity import retry, stop_after_attempt, wait_fixed, before_log, retry_if_exception_type

from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.events import ProcessedTransactionsCompletedEvent
from portfolio_common.db import get_async_db_session
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.outbox_repository import OutboxRepository
from portfolio_common.config import KAFKA_POSITION_HISTORY_PERSISTED_TOPIC

from ..core.position_logic import PositionLogic
from ..repositories.position_repository import PositionRepository
from ..repositories.state_store_repo import StateStoreRepository

logger = logging.getLogger(__name__)

SERVICE_NAME = "position-calculator"

class TransactionEventConsumer(BaseConsumer):
    """
    Consumes processed transaction completion events and updates/maintains position history.
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
            event = ProcessedTransactionsCompletedEvent.model_validate(data)

            async for db in get_async_db_session():
                tx = await db.begin()
                try:
                    idempotency_repo = IdempotencyRepository(db)
                    outbox_repo = OutboxRepository()
                    repo = PositionRepository(db)
                    state_repo = StateStoreRepository(db)

                    if await idempotency_repo.is_event_processed(event_id, SERVICE_NAME):
                        logger.warning("Event already processed. Skipping.")
                        await tx.rollback()
                        return

                    logic = PositionLogic(repo, state_repo)
                    await logic.apply_transactions_and_persist(event.portfolio_id, event.transactions)

                    outbox_repo.create_outbox_event(
                        db_session=db,
                        aggregate_type='PositionHistory',
                        aggregate_id=event.portfolio_id,
                        event_type='PositionHistoryPersisted',
                        topic=KAFKA_POSITION_HISTORY_PERSISTED_TOPIC,
                        payload={"portfolio_id": event.portfolio_id},
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
            logger.error("Invalid ProcessedTransactionsCompletedEvent; sending to DLQ.", exc_info=True)
            await self._send_to_dlq_async(msg, ValueError("invalid payload"))
        except (DBAPIError, IntegrityError):
            logger.warning("DB error; will retry...", exc_info=False)
            raise
        except Exception as e:
            logger.error("Unexpected error in position calculator; sending to DLQ.", exc_info=True)
            await self._send_to_dlq_async(msg, e)
