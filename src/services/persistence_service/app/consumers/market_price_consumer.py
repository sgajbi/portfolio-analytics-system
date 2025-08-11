# src/services/persistence_service/app/consumers/market_price_consumer.py
import logging
import json
from pydantic import ValidationError
from confluent_kafka import Message
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError
from tenacity import retry, stop_after_attempt, wait_exponential, before_log, retry_if_exception_type

from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.events import MarketPriceEvent
from portfolio_common.db import get_async_db_session
from ..repositories.market_price_repository import MarketPriceRepository
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.valuation_job_repository import ValuationJobRepository

logger = logging.getLogger(__name__)

SERVICE_NAME = "persistence-market-prices"

class MarketPriceConsumer(BaseConsumer):
    """
    A concrete consumer for validating, persisting market price events,
    and creating valuation jobs for all affected portfolios.
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
        stop=stop_after_attempt(3), 
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
                    valuation_job_repo = ValuationJobRepository(db)

                    if await idempotency_repo.is_event_processed(event_id, SERVICE_NAME):
                        logger.warning(
                            "Event has already been processed. Skipping.",
                            extra={"event_id": event_id, "service_name": SERVICE_NAME},
                        )
                        await tx.rollback()
                        return

                    await repo.create_market_price(event)

                    affected_portfolios = await repo.find_portfolios_holding_security_on_date(
                        security_id=event.security_id,
                        price_date=event.price_date
                    )

                    for portfolio_id in affected_portfolios:
                        await valuation_job_repo.upsert_job(
                            portfolio_id=portfolio_id,
                            security_id=event.security_id,
                            valuation_date=event.price_date,
                            correlation_id=correlation_id
                        )
                    
                    if affected_portfolios:
                        logger.info(f"Created {len(affected_portfolios)} valuation jobs for security {event.security_id} on {event.price_date}")

                    await idempotency_repo.mark_event_processed(
                        event_id=event_id,
                        portfolio_id="N/A",
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