# services/persistence_service/app/consumers/instrument_consumer.py
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
        """
        key = msg.key().decode('utf-8') if msg.key() else "NoKey"
        value = msg.value().decode('utf-8')
        
        try:
            instrument_data = json.loads(value)
            event = InstrumentEvent.model_validate(instrument_data)
            logger.info("Successfully validated event", extra={"security_id": event.security_id})

            with next(get_db_session()) as db:
                repo = InstrumentRepository(db)
                repo.create_or_update_instrument(event)
            
            logger.info("Successfully persisted", extra={"security_id": event.security_id})

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error("Message validation failed. Sending to DLQ.", extra={"key": key}, exc_info=True)
            await self._send_to_dlq(msg, e)