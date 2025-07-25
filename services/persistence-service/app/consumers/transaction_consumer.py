# services/persistence-service/app/consumers/transaction_consumer.py
import logging
import json
from pydantic import ValidationError
from confluent_kafka import Message

from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.events import TransactionEvent
from portfolio_common.db import get_db_session
from ..repositories.transaction_db_repo import TransactionDBRepository

logger = logging.getLogger(__name__)

class TransactionPersistenceConsumer(BaseConsumer):
    """
    A concrete consumer for validating and persisting raw transaction events.
    """
    async def process_message(self, msg: Message):
        """
        Processes a single raw transaction message from Kafka.
        It validates the message and persists it to the database.
        """
        key = msg.key().decode('utf-8') if msg.key() else "NoKey"
        value = msg.value().decode('utf-8')
        
        try:
            # 1. Validate the incoming message using our shared Pydantic event model
            transaction_data = json.loads(value)
            event = TransactionEvent.model_validate(transaction_data)
            logger.info(f"Successfully validated event for transaction_id: {event.transaction_id}")

            # 2. Persist to the database using the repository
            with next(get_db_session()) as db:
                repo = TransactionDBRepository(db)
                repo.create_or_update_transaction(event)
            
            logger.info(f"Successfully persisted transaction_id: {event.transaction_id}")

        except json.JSONDecodeError:
            logger.error(f"Failed to decode JSON for message with key '{key}'. Value: '{value}'")
        except ValidationError as e:
            logger.error(f"Message validation failed for key '{key}': {e}. Value: '{value}'")
        except Exception as e:
            logger.error(f"An unexpected error occurred processing message with key '{key}': {e}", exc_info=True)