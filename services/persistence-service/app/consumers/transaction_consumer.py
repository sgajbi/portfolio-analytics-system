# services/persistence-service/app/consumers/transaction_consumer.py
import logging
import json
from pydantic import ValidationError
from confluent_kafka import Message

from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.events import TransactionEvent
from portfolio_common.db import get_db_session
from portfolio_common.kafka_utils import get_kafka_producer
from portfolio_common.config import KAFKA_RAW_TRANSACTIONS_COMPLETED_TOPIC
from ..repositories.transaction_db_repo import TransactionDBRepository

logger = logging.getLogger(__name__)

class TransactionPersistenceConsumer(BaseConsumer):
    """
    A concrete consumer for validating and persisting raw transaction events.
    It also publishes a completion event after successful persistence.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._producer = get_kafka_producer()

    async def process_message(self, msg: Message):
        """
        Processes a single raw transaction message from Kafka.
        It validates the message, persists it, and publishes a completion event.
        """
        key = msg.key().decode('utf-8') if msg.key() else "NoKey"
        value = msg.value().decode('utf-8')
        
        try:
            # 1. Validate the incoming message
            transaction_data = json.loads(value)
            event = TransactionEvent.model_validate(transaction_data)
            logger.info(f"Successfully validated event for transaction_id: {event.transaction_id}")

            # 2. Persist to the database
            with next(get_db_session()) as db:
                repo = TransactionDBRepository(db)
                repo.create_or_update_transaction(event)
            
            logger.info(f"Successfully persisted transaction_id: {event.transaction_id}")

            # 3. Publish completion event
            self._producer.publish_message(
                topic=KAFKA_RAW_TRANSACTIONS_COMPLETED_TOPIC,
                key=event.transaction_id,
                value=event.model_dump(mode='json')
            )
            logger.info(f"Published completion event for transaction_id: {event.transaction_id}")
            self._producer.flush(timeout=5)


        except json.JSONDecodeError:
            logger.error(f"Failed to decode JSON for message with key '{key}'. Value: '{value}'")
        except ValidationError as e:
            logger.error(f"Message validation failed for key '{key}': {e}. Value: '{value}'")
        except Exception as e:
            logger.error(f"An unexpected error occurred processing message with key '{key}': {e}", exc_info=True)