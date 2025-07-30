import structlog
import json
from pydantic import ValidationError
from confluent_kafka import Message

from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.events import FxRateEvent
from portfolio_common.db import get_db_session
from ..repositories.fx_rate_repository import FxRateRepository

logger = structlog.get_logger(__name__)

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
            logger.info(
                "Successfully validated event for FX rate", 
                from_currency=event.from_currency,
                to_currency=event.to_currency,
                rate_date=event.rate_date
            )

            with next(get_db_session()) as db:
                repo = FxRateRepository(db)
                repo.create_fx_rate(event)
            
        except (json.JSONDecodeError, ValidationError) as e:
            logger.error("Message validation failed. Sending to DLQ.", key=key, error=str(e))
            await self._send_to_dlq(msg, e)