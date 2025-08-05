# services/persistence_service/app/consumers/market_price_consumer.py
import logging
import json
import asyncio
from pydantic import ValidationError
from confluent_kafka import Message
from sqlalchemy.exc import DBAPIError, IntegrityError
from tenacity import retry, stop_after_attempt, wait_exponential, before_log, retry_if_exception_type

from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.events import MarketPriceEvent
from portfolio_common.db import get_db_session
from portfolio_common.config import KAFKA_MARKET_PRICE_PERSISTED_TOPIC
from ..repositories.market_price_repository import MarketPriceRepository
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.outbox_repository import OutboxRepository

logger = logging.getLogger(__name__)

SERVICE_NAME = "persistence-market-prices"

class MarketPriceConsumer(BaseConsumer):
    """
    A concrete consumer for validating and persisting market price events.
    """
    def process_message(self, msg: Message, loop: asyncio.AbstractEventLoop):
        """Wrapper to call the retryable logic."""
        try:
            self._process_message_with_retry(msg, loop)
        except Exception as e:
            logger.error(f"Fatal error for market price after retries. Sending to DLQ. Key={msg.key()}", exc_info=True)
            self._send_to_dlq_sync(msg, e, loop)
    
    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10), 
        stop=stop_after_attempt(3), 
        before=before_log(logger, logging.INFO),
        retry=retry_if_exception_type((DBAPIError, IntegrityError)),
        reraise=True
    )
    def _process_message_with_retry(self, msg: Message, loop: asyncio.AbstractEventLoop):
        key = msg.key().decode('utf-8') if msg.key() else "NoKey"
        value = msg.value().decode('utf-8')
        correlation_id = correlation_id_var.get()
        event = None
        event_id = f"{msg.topic()}-{msg.partition()}-{msg.offset()}"
        
        logger.info("MarketPriceConsumer received message", 
            extra={"key": key, "event_id": event_id})

        try:
            market_price_data = json.loads(value)
            event = MarketPriceEvent.model_validate(market_price_data)
            logger.info("Successfully validated event", 
                extra={"security_id": event.security_id, "price_date": event.price_date})

            with next(get_db_session()) as db:
                with db.begin():
                    repo = MarketPriceRepository(db)
                    idempotency_repo = IdempotencyRepository(db)
                    outbox_repo = OutboxRepository()

                    if idempotency_repo.is_event_processed(event_id, SERVICE_NAME):
                        logger.warning(
                            "Event has already been processed. Skipping.",
                            extra={"event_id": event_id, "service_name": SERVICE_NAME}
                        )
                        return

                    repo.create_market_price(event)
            
                    outbox_repo.create_outbox_event(
                        db_session=db,
                        aggregate_type='MarketPrice',
                        aggregate_id=event.security_id,
                        event_type='MarketPricePersisted',
                        topic=KAFKA_MARKET_PRICE_PERSISTED_TOPIC,
                        payload=event.model_dump(mode='json'),
                        correlation_id=correlation_id
                    )

                    idempotency_repo.mark_event_processed(
                        event_id=event_id,
                        portfolio_id="N/A", 
                        service_name=SERVICE_NAME,
                        correlation_id=correlation_id
                    )

            logger.info("Database transaction for market price was successful.")

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error("Message validation failed. Sending to DLQ.", 
                extra={"key": key, "event_id": event_id}, exc_info=True)
            self._send_to_dlq_sync(msg, e, loop)
        except (DBAPIError, IntegrityError):
            logger.warning(f"Caught a DB error for price {getattr(event, 'security_id', 'UNKNOWN')}. Will retry...",
                extra={"event_id": event_id})
            raise
        except Exception as e:
            logger.error(f"An unexpected error occurred for price {getattr(event, 'security_id', 'UNKNOWN')}. Sending to DLQ.", 
                extra={"key": key, "event_id": event_id}, exc_info=True)
            self._send_to_dlq_sync(msg, e, loop)