import logging
import json
from pydantic import ValidationError
from confluent_kafka import Message

from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.events import FxRateEvent
from portfolio_common.db import get_db_session
from ..repositories.fx_rate_repository import FxRateRepository

logger = logging.getLogger(__name__)

class FxRateConsumer(BaseConsumer):
    """
    A concrete consumer for validating and persisting FX rate events.
    """
    async def process_message(self, msg: Message):
        """
        Processes a single FX rate message from Kafka.
        It validates the message and persists it to the database.
        """
        key = msg.key().decode('utf-8') if msg.key() else "NoKey"
        value = msg.value().decode('utf-8')
        
        try:
            # 1. Validate the incoming message using the Pydantic event model
            fx_rate_data = json.loads(value)
            event = FxRateEvent.model_validate(fx_rate_data)
            logger.info(f"Successfully validated event for FX rate: {event.from_currency}-{event.to_currency} on {event.rate_date}")

            # 2. Persist to the database using the repository
            with next(get_db_session()) as db:
                repo = FxRateRepository(db)
                repo.create_fx_rate(event)
            
        except json.JSONDecodeError:
            logger.error(f"Failed to decode JSON for message with key '{key}'. Value: '{value}'")
        except ValidationError as e:
            logger.error(f"Message validation failed for key '{key}': {e}. Value: '{value}'")
        except Exception as e:
            logger.error(f"An unexpected error occurred processing message with key '{key}': {e}", exc_info=True)