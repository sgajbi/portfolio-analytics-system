import structlog
import json
from pydantic import ValidationError
from confluent_kafka import Message

from portfolio_common.kafka_consumer import BaseConsumer, correlation_id_cv # Import correlation_id_cv
from portfolio_common.events import MarketPriceEvent
from portfolio_common.db import get_db_session
from portfolio_common.config import KAFKA_MARKET_PRICE_PERSISTED_TOPIC
from ..repositories.market_price_repository import MarketPriceRepository

logger = structlog.get_logger(__name__)

class MarketPriceConsumer(BaseConsumer):
    """
    A concrete consumer for validating and persisting market price events.
    Publishes a completion event on success.
    """
    async def process_message(self, msg: Message):
        """
        Processes a single market price message from Kafka.
        """
        key = msg.key().decode('utf-8') if msg.key() else "NoKey"
        value = msg.value().decode('utf-8')
        logger.info("MarketPriceConsumer received message", key=key)

        try:
            market_price_data = json.loads(value)
            event = MarketPriceEvent.model_validate(market_price_data)
            logger.info("Successfully validated event", security_id=event.security_id, price_date=event.price_date)

            with next(get_db_session()) as db:
                with db.begin(): # Use a transactional block for atomicity
                    repo = MarketPriceRepository(db)
                    repo.create_market_price(event)
            
            logger.info("Database transaction for market price was successful.")
            
            if self._producer:
                # --- FIX: Get correlation ID from context and create headers ---
                corr_id = correlation_id_cv.get()
                headers = [('X-Correlation-ID', corr_id.encode('utf-8'))] if corr_id else None

                self._producer.publish_message(
                    topic=KAFKA_MARKET_PRICE_PERSISTED_TOPIC,
                    key=event.security_id,
                    value=event.model_dump(mode='json'),
                    headers=headers # Pass headers to the producer
                )
                logger.info("Published market_price_persisted event", security_id=event.security_id)
                self._producer.flush(timeout=5)
            else:
                logger.warning("Kafka producer not available, skipping completion event.")

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error("Message validation failed. Sending to DLQ.", key=key, error=str(e), exc_info=True)
            await self._send_to_dlq(msg, e)
        except Exception as e:
            logger.error("An unexpected error occurred. Sending to DLQ.", key=key, error=str(e), exc_info=True)
            await self._send_to_dlq(msg, e)