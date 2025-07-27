import logging
import json
from pydantic import ValidationError
from confluent_kafka import Message

from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.events import MarketPriceEvent
from portfolio_common.db import get_db_session
from portfolio_common.config import KAFKA_MARKET_PRICE_PERSISTED_TOPIC
from ..repositories.market_price_repository import MarketPriceRepository

logger = logging.getLogger(__name__)

class MarketPriceConsumer(BaseConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self._producer:
            from portfolio_common.kafka_utils import get_kafka_producer
            self._producer = get_kafka_producer()

    async def process_message(self, msg: Message):
        key = msg.key().decode('utf-8') if msg.key() else "NoKey"
        value = msg.value().decode('utf-8')
        logger.info(f"MarketPriceConsumer received message with key '{key}'")

        try:
            market_price_data = json.loads(value)
            logger.info("DEBUG: Message JSON decoded successfully.")
            
            event = MarketPriceEvent.model_validate(market_price_data)
            logger.info(f"DEBUG: Pydantic model validated for security_id: {event.security_id}")

            with next(get_db_session()) as db:
                with db.begin():
                    repo = MarketPriceRepository(db)
                    logger.info("DEBUG: Calling repository to create market price.")
                    repo.create_market_price(event)
            
            logger.info("DEBUG: Database transaction committed successfully.")
            
            self._producer.publish_message(
                topic=KAFKA_MARKET_PRICE_PERSISTED_TOPIC,
                key=event.security_id,
                value=event.model_dump(mode='json')
            )
            logger.info(f"Published market_price_persisted event for {event.security_id}")
            self._producer.flush(timeout=5)

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"Message validation failed for key '{key}': {e}. Sending to DLQ.", exc_info=True)
            await self._send_to_dlq(msg, e)
        except Exception as e:
            logger.error(f"An unexpected error occurred for key '{key}': {e}", exc_info=True)
            await self._send_to_dlq(msg, e)