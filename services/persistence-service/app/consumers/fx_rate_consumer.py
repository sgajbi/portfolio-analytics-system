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
        """
        key = msg.key().decode('utf-8') if msg.key() else "NoKey"
        value = msg.value().decode('utf-8')
        
        try:
            fx_rate_data = json.loads(value)
            event = FxRateEvent.model_validate(fx_rate_data)
            logger.info(f"Successfully validated event for FX rate: {event.from_currency}-{event.to_currency} on {event.rate_date}")

            with next(get_db_session()) as db:
                repo = FxRateRepository(db)
                repo.create_fx_rate(event)
            
        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"Message validation failed for key '{key}': {e}. Sending to DLQ.")
            await self._send_to_dlq(msg, e)