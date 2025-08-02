# services/persistence_service/app/consumers/transaction_consumer.py
import logging
import json
import asyncio
from pydantic import ValidationError
from confluent_kafka import Message
from sqlalchemy.exc import IntegrityError
from tenacity import retry, stop_after_attempt, wait_fixed, before_log

from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.events import TransactionEvent
from portfolio_common.db import get_db_session
from portfolio_common.config import KAFKA_RAW_TRANSACTIONS_COMPLETED_TOPIC
from ..repositories.transaction_db_repo import TransactionDBRepository
from portfolio_common.outbox_repository import OutboxRepository


logger = logging.getLogger(__name__)

class TransactionPersistenceConsumer(BaseConsumer):
    """
    A concrete consumer for validating and persisting raw transaction events.
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
        wait=wait_fixed(2),
        stop=stop_after_attempt(3),
        before=before_log(logger, logging.INFO),
    )
    def _process_message_with_retry(self, msg: Message, loop: asyncio.AbstractEventLoop):
        """
        Processes a single raw transaction message from Kafka.
        """
        key = msg.key().decode('utf-8') if msg.key() else "NoKey"
        value = msg.value().decode('utf-8')
        correlation_id = correlation_id_var.get()
        event = None
        
        try:
            # 1. Validate the incoming message
            transaction_data = json.loads(value)
            event = TransactionEvent.model_validate(transaction_data)
            logger.info("Successfully validated event", 
                extra={"transaction_id": event.transaction_id})

            # 2. Persist to DB and write to outbox in a single transaction
            with next(get_db_session()) as db:
                with db.begin(): # Atomically commit or rollback
                    repo = TransactionDBRepository(db)
                    outbox_repo = OutboxRepository()

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

            logger.info(
                "Successfully persisted transaction and staged outbox event.",
                extra={"transaction_id": event.transaction_id}
            )

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error("Message validation failed. Sending to DLQ.", extra={"key": key}, exc_info=True)
            self._send_to_dlq_sync(msg, e, loop)
        except IntegrityError:
            logger.warning(
                "Caught IntegrityError, likely a race condition. Will retry...",
                extra={"transaction_id": getattr(event, 'transaction_id', 'UNKNOWN')},
            )
            raise
        except Exception as e:
            logger.error(f"An unexpected error occurred for transaction {getattr(event, 'transaction_id', 'UNKNOWN')}. Sending to DLQ.", exc_info=True)
            self._send_to_dlq_sync(msg, e, loop)
