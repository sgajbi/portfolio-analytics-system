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
    """
    A concrete consumer for validating and persisting market price events.
    Publishes a completion event on success.
    """
    # NO custom __init__ method. We will rely on the BaseConsumer's __init__
    # to correctly set up the consumer and the self._producer for the DLQ.
    # That same producer can be used to publish the completion event.

    async def process_message(self, msg: Message):
        """
        Processes a single market price message from Kafka.
        """
        key = msg.key().decode('utf-8') if msg.key() else "NoKey"
        value = msg.value().decode('utf-8')
        logger.info(f"MarketPriceConsumer received message with key '{key}'")

        try:
            market_price_data = json.loads(value)
            event = MarketPriceEvent.model_validate(market_price_data)
            logger.info(f"Successfully validated event for security_id: {event.security_id} on {event.price_date}")

            with next(get_db_session()) as db:
                with db.begin(): # Use a transactional block for atomicity
                    repo = MarketPriceRepository(db)
                    repo.create_market_price(event)
            
            logger.info("Database transaction for market price was successful.")
            
            # Publish completion event only after a successful commit
            if self._producer:
                self._producer.publish_message(
                    topic=KAFKA_MARKET_PRICE_PERSISTED_TOPIC,
                    key=event.security_id,
                    value=event.model_dump(mode='json')
                )
                logger.info(f"Published market_price_persisted event for {event.security_id}")
                self._producer.flush(timeout=5)
            else:
                logger.warning("Kafka producer not available, skipping completion event.")

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"Message validation failed for key '{key}': {e}. Sending to DLQ.", exc_info=True)
            await self._send_to_dlq(msg, e)
        except Exception as e:
            logger.error(f"An unexpected error occurred for key '{key}': {e}", exc_info=True)
            await self._send_to_dlq(msg, e)