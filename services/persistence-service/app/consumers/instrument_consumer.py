import logging
import json
from pydantic import ValidationError
from confluent_kafka import Message

from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.events import InstrumentEvent
from portfolio_common.db import get_db_session
from ..repositories.instrument_repository import InstrumentRepository

logger = logging.getLogger(__name__)

class InstrumentConsumer(BaseConsumer):
    """
    A concrete consumer for validating and persisting instrument events.
    """
    async def process_message(self, msg: Message):
        """
        Processes a single instrument message from Kafka.
        It validates the message and persists it to the database.
        """
        key = msg.key().decode('utf-8') if msg.key() else "NoKey"
        value = msg.value().decode('utf-8')
        
        try:
            # 1. Validate the incoming message using our shared Pydantic event model
            instrument_data = json.loads(value)
            event = InstrumentEvent.model_validate(instrument_data)
            logger.info(f"Successfully validated event for security_id: {event.security_id}")

            # 2. Persist to the database using the repository
            with next(get_db_session()) as db:
                repo = InstrumentRepository(db)
                repo.create_or_update_instrument(event)
            
            logger.info(f"Successfully persisted security_id: {event.security_id}")

        except json.JSONDecodeError:
            logger.error(f"Failed to decode JSON for message with key '{key}'. Value: '{value}'")
        except ValidationError as e:
            logger.error(f"Message validation failed for key '{key}': {e}. Value: '{value}'")
        except Exception as e:
            logger.error(f"An unexpected error occurred processing message with key '{key}': {e}", exc_info=True)