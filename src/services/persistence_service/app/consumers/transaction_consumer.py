# src/services/persistence_service/app/consumers/transaction_consumer.py
import logging
import json
import sys
from pydantic import ValidationError
from confluent_kafka import Message
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError
from tenacity import retry, stop_after_attempt, wait_exponential, before_log, retry_if_exception_type

from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.events import TransactionEvent
from portfolio_common.db import get_async_db_session
from portfolio_common.config import KAFKA_RAW_TRANSACTIONS_COMPLETED_TOPIC
from ..repositories.transaction_db_repo import TransactionDBRepository
from portfolio_common.outbox_repository import OutboxRepository
from portfolio_common.idempotency_repository import IdempotencyRepository

logger = logging.getLogger(__name__)

SERVICE_NAME = "persistence-transactions"

class PortfolioNotFoundError(Exception):
    """Custom exception to signal a retryable condition."""
    pass

class TransactionPersistenceConsumer(BaseConsumer):
    """
    A concrete consumer for validating and persisting raw transaction events.
    """
    async def process_message(self, msg: Message):
        try:
            await self._process_message_with_retry(msg)
        except (OperationalError, DBAPIError):
            logger.critical(
                "Unrecoverable database error after all retries. Shutting down service.",
                extra={"key": msg.key().decode('utf-8') if msg.key() else "NoKey"},
                exc_info=True
            )
            sys.exit(1)
        except Exception as e:
            logger.error(f"Fatal error for transaction after retries. Sending to DLQ. Key={msg.key()}", exc_info=True)
            await self._send_to_dlq_async(msg, e)

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(5),
        before=before_log(logger, logging.INFO),
        retry=retry_if_exception_type((DBAPIError, IntegrityError, PortfolioNotFoundError, OperationalError)),
        reraise=True
    )
    async def _process_message_with_retry(self, msg: Message):
        key = msg.key().decode('utf-8') if msg.key() else "NoKey"
        value = msg.value().decode('utf-8')
        correlation_id = correlation_id_var.get()
        event = None
        
        try:
            transaction_data = json.loads(value)
            event = TransactionEvent.model_validate(transaction_data)
            
            event_id = event.transaction_id
            
            logger.info(
                "Successfully validated event",
                extra={"transaction_id": event.transaction_id, "event_id": event_id}
            )

            async for db in get_async_db_session():
                tx = await db.begin()
                try:
                    repo = TransactionDBRepository(db)
                    outbox_repo = OutboxRepository(db)
                    idempotency_repo = IdempotencyRepository(db)

                    if await idempotency_repo.is_event_processed(event_id, SERVICE_NAME):
                        logger.warning(
                            "Event has already been processed. Skipping.",
                            extra={"event_id": event_id, "service_name": SERVICE_NAME},
                        )
                        await tx.rollback()
                        return

                    portfolio_exists = await repo.check_portfolio_exists(event.portfolio_id)
                    if not portfolio_exists:
                        raise PortfolioNotFoundError(
                            f"Portfolio {event.portfolio_id} not found for transaction {event.transaction_id}. Retrying..."
                        )

                    await repo.create_or_update_transaction(event)

                    await outbox_repo.create_outbox_event(
                        aggregate_type='RawTransaction',
                        aggregate_id=str(event.portfolio_id),
                        event_type='RawTransactionPersisted',
                        topic=KAFKA_RAW_TRANSACTIONS_COMPLETED_TOPIC,
                        payload=event.model_dump(mode='json'),
                        correlation_id=correlation_id
                    )

                    await idempotency_repo.mark_event_processed(
                        event_id=event_id,
                        portfolio_id=event.portfolio_id,
                        service_name=SERVICE_NAME,
                        correlation_id=correlation_id
                    )

                    await db.commit()
                except Exception:
                    await tx.rollback()
                    raise

            logger.info(
                "Successfully persisted transaction and marked event as processed",
                extra={"transaction_id": event.transaction_id, "event_id": event_id}
            )

        except (json.JSONDecodeError, ValidationError) as e:
            kafka_event_id = f"{msg.topic()}-{msg.partition()}-{msg.offset()}"
            logger.error(
                "Message validation failed. Sending to DLQ.",
                extra={"key": key, "event_id": kafka_event_id}, exc_info=True
            )
            await self._send_to_dlq_async(msg, e)
        except (DBAPIError, IntegrityError, PortfolioNotFoundError, OperationalError) as e:
            logger.warning(
                f"Caught a DB error for transaction {getattr(event, 'transaction_id', 'UNKNOWN')}: {e}. Will retry...",
                extra={"event_id": getattr(event, 'transaction_id', 'UNKNOWN')},
            )
            raise
        except Exception as e:
            kafka_event_id = f"{msg.topic()}-{msg.partition()}-{msg.offset()}"
            logger.error(
                f"Unexpected error processing message for transaction {getattr(event, 'transaction_id', 'UNKNOWN')}. Sending to DLQ.",
                extra={"key": key, "event_id": kafka_event_id}, exc_info=True
            )
            await self._send_to_dlq_async(msg, e)