# services/persistence_service/app/consumers/market_price_consumer.py
import logging
import json
import asyncio
from pydantic import ValidationError
from confluent_kafka import Message
from sqlalchemy.exc import IntegrityError
from tenacity import retry, stop_after_attempt, wait_fixed

from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.logging_utils import correlation_id_var
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
    def process_message(self, msg: Message, loop: asyncio.AbstractEventLoop):
        """Wrapper to call the retryable logic."""
        self._process_message_with_retry(msg, loop)
    
    @retry(wait=wait_fixed(2), stop=stop_after_attempt(3))
    def _process_message_with_retry(self, msg: Message, loop: asyncio.AbstractEventLoop):
        key = msg.key().decode('utf-8') if msg.key() else "NoKey"
        value = msg.value().decode('utf-8')
        event = None
        logger.info("MarketPriceConsumer received message", extra={"key": key})

        try:
            market_price_data = json.loads(value)
            event = MarketPriceEvent.model_validate(market_price_data)
            logger.info("Successfully validated event", extra={"security_id": event.security_id, "price_date": event.price_date})

            with next(get_db_session()) as db:
                with db.begin():
                    repo = MarketPriceRepository(db)
                    repo.create_market_price(event)
            
            logger.info("Database transaction for market price was successful.")
            
            if self._producer:
                corr_id = correlation_id_var.get()
                headers = [('correlation_id', corr_id.encode('utf-8'))] if corr_id else None

                self._producer.publish_message(
                    topic=KAFKA_MARKET_PRICE_PERSISTED_TOPIC,
                    key=event.security_id,
                    value=event.model_dump(mode='json'),
                    headers=headers
                )
                logger.info("Published market_price_persisted event", extra={"security_id": event.security_id})
                self._producer.flush(timeout=5)
            else:
                logger.warning("Kafka producer not available, skipping completion event.")

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error("Message validation failed. Sending to DLQ.", extra={"key": key}, exc_info=True)
            self._send_to_dlq_sync(msg, e, loop)
        except IntegrityError:
            logger.warning(f"Caught IntegrityError for price {getattr(event, 'security_id', 'UNKNOWN')}. Will retry...")
            raise
        except Exception as e:
            logger.error(f"An unexpected error occurred for price {getattr(event, 'security_id', 'UNKNOWN')}. Sending to DLQ.", extra={"key": key}, exc_info=True)
            self._send_to_dlq_sync(msg, e, loop)