# services/persistence-service/app/consumers/transaction_consumer.py
import structlog
import json
from pydantic import ValidationError
from confluent_kafka import Message

from portfolio_common.kafka_consumer import BaseConsumer, correlation_id_cv # Import correlation_id_cv
from portfolio_common.events import TransactionEvent
from portfolio_common.db import get_db_session
from portfolio_common.config import KAFKA_RAW_TRANSACTIONS_COMPLETED_TOPIC
from ..repositories.transaction_db_repo import TransactionDBRepository

logger = structlog.get_logger(__name__)

class TransactionPersistenceConsumer(BaseConsumer):
    """
    A concrete consumer for validating and persisting raw transaction events.
    - On success, it publishes a completion event.
    - On validation failure, it publishes the message to a DLQ.
    """
    async def process_message(self, msg: Message):
        """
        Processes a single raw transaction message from Kafka.
        """
        key = msg.key().decode('utf-8') if msg.key() else "NoKey"
        value = msg.value().decode('utf-8')
        
        try:
            # 1. Validate the incoming message
            transaction_data = json.loads(value)
            event = TransactionEvent.model_validate(transaction_data)
            logger.info("Successfully validated event", transaction_id=event.transaction_id)

            # 2. Persist to the database
            with next(get_db_session()) as db:
                repo = TransactionDBRepository(db)
                repo.create_or_update_transaction(event)
            
            logger.info("Successfully persisted transaction", transaction_id=event.transaction_id)

            # 3. Publish completion event
            if self._producer:
                partition_key = event.portfolio_id
                
                # --- FIX: Get correlation ID from context and create headers ---
                corr_id = correlation_id_cv.get()
                headers = [('X-Correlation-ID', corr_id.encode('utf-8'))] if corr_id else None
                
                self._producer.publish_message(
                    topic=KAFKA_RAW_TRANSACTIONS_COMPLETED_TOPIC,
                    key=partition_key,
                    value=event.model_dump(mode='json'),
                    headers=headers # Pass headers to the producer
                )
                logger.info(
                    "Published completion event", 
                    transaction_id=event.transaction_id, 
                    partition_key=partition_key
                )
                self._producer.flush(timeout=5)

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error("Message validation failed. Sending to DLQ.", key=key, error=str(e))
            await self._send_to_dlq(msg, e)