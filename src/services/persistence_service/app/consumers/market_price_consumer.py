# src/services/persistence_service/app/consumers/market_price_consumer.py
import logging
import json
from pydantic import ValidationError
from confluent_kafka import Message
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError
from tenacity import retry, stop_after_delay, wait_exponential, before_log, retry_if_exception_type

from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.events import MarketPriceEvent, MarketPricePersistedEvent
from portfolio_common.db import get_async_db_session
from ..repositories.market_price_repository import MarketPriceRepository
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.outbox_repository import OutboxRepository
from portfolio_common.config import KAFKA_MARKET_PRICE_PERSISTED_TOPIC

logger = logging.getLogger(__name__)

SERVICE_NAME = "persistence-market-prices"

class MarketPriceConsumer(BaseConsumer):
    """
    A concrete consumer for validating and persisting market price events.
    Upon successful persistence, it publishes a `market_price_persisted` event.
    """
    async def process_message(self, msg: Message):
        """Wrapper to call the retryable logic."""
        try:
            await self._process_message_with_retry(msg)
        except Exception as e:
            logger.error(f"Fatal error for market price after retries. Sending to DLQ. Key={msg.key()}", exc_info=True)
            await self._send_to_dlq_async(msg, e)
    
    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_delay(300),
        before=before_log(logger, logging.INFO),
        retry=retry_if_exception_type((DBAPIError, IntegrityError, OperationalError)),
        reraise=True
    )
    async def _process_message_with_retry(self, msg: Message):
        key = msg.key().decode('utf-8') if msg.key() else "NoKey"
        value = msg.value().decode('utf-8')
        correlation_id = correlation_id_var.get()
        event = None
        event_id = f"{msg.topic()}-{msg.partition()}-{msg.offset()}"

        logger.info("MarketPriceConsumer received message", extra={"key": key, "event_id": event_id})

        try:
            market_price_data = json.loads(value)
            event = MarketPriceEvent.model_validate(market_price_data)
            logger.info(
                "Successfully validated event",
                extra={"security_id": event.security_id, "price_date": event.price_date},
            )

            async for db in get_async_db_session():
                tx = await db.begin()
                try:
                    repo = MarketPriceRepository(db)
                    idempotency_repo = IdempotencyRepository(db)
                    outbox_repo = OutboxRepository(db)

                    if await idempotency_repo.is_event_processed(event_id, SERVICE_NAME):
                        logger.warning(
                            "Event has already been processed. Skipping.",
                            extra={"event_id": event_id, "service_name": SERVICE_NAME},
                        )
                        await tx.rollback()
                        return

                    persisted_price = await repo.create_market_price(event)
                    
                    # Create the outbound event payload from the persisted data
                    outbound_event = MarketPricePersistedEvent.model_validate(persisted_price, from_attributes=True)
                    
                    # Create an outbox event to announce the persistence
                    await outbox_repo.create_outbox_event(
                        aggregate_type='MarketPrice',
                        aggregate_id=persisted_price.security_id,
                        event_type='MarketPricePersisted',
                        topic=KAFKA_MARKET_PRICE_PERSISTED_TOPIC,
                        payload=outbound_event.model_dump(mode='json'),
                        correlation_id=correlation_id
                    )

                    await idempotency_repo.mark_event_processed(
                        event_id=event_id,
                        portfolio_id="N/A", # Market prices are not portfolio-specific at this stage
                        service_name=SERVICE_NAME,
                        correlation_id=correlation_id,
                    )

                    await db.commit()
                except Exception:
                    await tx.rollback()
                    raise

            logger.info("Database transaction for market price was successful.")

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(
                "Message validation failed. Sending to DLQ.",
                extra={"key": key, "event_id": event_id},
                exc_info=True,
            )
            await self._send_to_dlq_async(msg, e)
        except (DBAPIError, IntegrityError, OperationalError):
            logger.warning(
                f"Caught a DB error for price {getattr(event, 'security_id', 'UNKNOWN')}. Will retry...",
                extra={"event_id": event_id},
            )
            raise
        except Exception as e:
            logger.error(
                f"An unexpected error occurred for price {getattr(event, 'security_id', 'UNKNOWN')}. Sending to DLQ.",
                extra={"key": key, "event_id": event_id},
                exc_info=True,
            )
            await self._send_to_dlq_async(msg, e)