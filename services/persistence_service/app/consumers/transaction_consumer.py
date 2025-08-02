# services/persistence-service/app/consumers/transaction_consumer.py
import logging
import json
from pydantic import ValidationError
from confluent_kafka import Message

from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.events import TransactionEvent
from portfolio_common.db import get_db_session
from portfolio_common.config import KAFKA_RAW_TRANSACTIONS_COMPLETED_TOPIC
from ..repositories.transaction_db_repo import TransactionDBRepository
# NEW: Import the OutboxRepository
from portfolio_common.outbox_repository import OutboxRepository


logger = logging.getLogger(__name__)

class TransactionPersistenceConsumer(BaseConsumer):
    """
    A concrete consumer for validating and persisting raw transaction events.
    - On success, it writes a completion event to the outbox table.
    - On validation failure, it publishes the message to a DLQ.
    """
    async def process_message(self, msg: Message):
        """
        Processes a single raw transaction message from Kafka.
        """
        key = msg.key().decode('utf-8') if msg.key() else "NoKey"
        value = msg.value().decode('utf-8')
        correlation_id = correlation_id_var.get()
        
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

                    # a. Persist the business data (transaction)
                    repo.create_or_update_transaction(event)
            
                    # b. Create the outbox event, now with correlation ID
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
            await self._send_to_dlq(msg, e)