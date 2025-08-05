# services/persistence_service/app/consumers/transaction_consumer.py
import logging
import json
import asyncio
from pydantic import ValidationError
from confluent_kafka import Message
from sqlalchemy.exc import IntegrityError
from tenacity import retry, stop_after_attempt, wait_exponential, before_log

from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.events import TransactionEvent
from portfolio_common.db import get_db_session
from portfolio_common.config import KAFKA_RAW_TRANSACTIONS_COMPLETED_TOPIC
from ..repositories.transaction_db_repo import TransactionDBRepository
from portfolio_common.outbox_repository import OutboxRepository
from portfolio_common.idempotency_repository import IdempotencyRepository

logger = logging.getLogger(__name__)

SERVICE_NAME = "persistence-transactions"

class TransactionPersistenceConsumer(BaseConsumer):
    """
    A concrete consumer for validating and persisting raw transaction events.
    - It uses an idempotency check to ensure exactly-once processing.
    - On success, it writes a completion event to the outbox table.
    - On validation failure, it publishes the message to a DLQ.
    - It retries on database integrity errors to handle race conditions.
    """
    def process_message(self, msg: Message, loop: asyncio.AbstractEventLoop):
        """
        Wrapper method to satisfy the abstract base class.
        It calls the actual processing logic which is decorated with tenacity.
        """
        self._process_message_with_retry(msg, loop)

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(3),
        before=before_log(logger, logging.INFO),
        reraise=True
    )
    def _process_message_with_retry(self, msg: Message, loop: asyncio.AbstractEventLoop):
        """
        Processes a single raw transaction message from Kafka atomically and idempotently.
        """
        key = msg.key().decode('utf-8') if msg.key() else "NoKey"
        value = msg.value().decode('utf-8')
        correlation_id = correlation_id_var.get()
        event = None

        event_id = f"{msg.topic()}-{msg.partition()}-{msg.offset()}"
        
        try:
            transaction_data = json.loads(value)
            event = TransactionEvent.model_validate(transaction_data)
            logger.info("Successfully validated event", 
                extra={"transaction_id": event.transaction_id, "event_id": event_id})

            with next(get_db_session()) as db:
                with db.begin(): 
                    repo = TransactionDBRepository(db)
                    outbox_repo = OutboxRepository()
                    idempotency_repo = IdempotencyRepository(db)

                    if idempotency_repo.is_event_processed(event_id, SERVICE_NAME):
                        logger.warning(
                            "Event has already been processed. Skipping.",
                            extra={"event_id": event_id, "service_name": SERVICE_NAME}
                        )
                        return

                    repo.create_or_update_transaction(event)
            
                    outbox_repo.create_outbox_event(
                        db_session=db,
                        aggregate_type='Transaction',
                        aggregate_id=event.transaction_id,
                        event_type='TransactionPersisted',
                        topic=KAFKA_RAW_TRANSACTIONS_COMPLETED_TOPIC,
                        payload=event.model_dump(mode='json'),
                        correlation_id=correlation_id
                    )

                    idempotency_repo.mark_event_processed(
                        event_id=event_id,
                        portfolio_id=event.portfolio_id,
                        service_name=SERVICE_NAME,
                        correlation_id=correlation_id
                    )

            logger.info(
                "Successfully persisted transaction, staged outbox event, and marked as processed.",
                extra={"transaction_id": event.transaction_id, "event_id": event_id}
            )

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error("Message validation failed. Sending to DLQ.", 
                extra={"key": key, "event_id": event_id}, exc_info=True)
            self._send_to_dlq_sync(msg, e, loop)
        except IntegrityError:
            logger.warning(
                "Caught IntegrityError, likely a race condition. Will retry...",
                extra={"transaction_id": getattr(event, 'transaction_id', 'UNKNOWN'), "event_id": event_id},
            )
            raise
        except Exception as e:
            logger.error(f"An unexpected error occurred for transaction {getattr(event, 'transaction_id', 'UNKNOWN')}. Sending to DLQ.", 
                extra={"event_id": event_id}, exc_info=True)
            self._send_to_dlq_sync(msg, e, loop)