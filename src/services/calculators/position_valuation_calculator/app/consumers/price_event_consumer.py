# src/services/calculators/position_valuation_calculator/app/consumers/price_event_consumer.py
import logging
import json
from datetime import timedelta

from pydantic import ValidationError
from confluent_kafka import Message
from sqlalchemy.exc import DBAPIError, OperationalError
from tenacity import retry, stop_after_attempt, wait_fixed, before_log, retry_if_exception_type

from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.events import MarketPricePersistedEvent
from portfolio_common.db import get_async_db_session
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.logging_utils import correlation_id_var
from ..repositories.valuation_repository import ValuationRepository
from ..repositories.instrument_reprocessing_state_repository import InstrumentReprocessingStateRepository

logger = logging.getLogger(__name__)

SERVICE_NAME = "price-event-reprocessing-trigger"

class PriceEventConsumer(BaseConsumer):
    """
    Consumes market price events. If a price is back-dated, it flags the
    instrument by upserting a record to the instrument_reprocessing_state table.
    This acts as a trigger for the ValuationScheduler.
    """
    @retry(
        wait=wait_fixed(3),
        stop=stop_after_attempt(5),
        before=before_log(logger, logging.INFO),
        retry=retry_if_exception_type((DBAPIError, OperationalError)),
        reraise=True
    )
    async def process_message(self, msg: Message):
        key = msg.key().decode('utf-8') if msg.key() else "NoKey"
        value = msg.value().decode('utf-8')
        event_id = f"{msg.topic()}-{msg.partition()}-{msg.offset()}"
        correlation_id = correlation_id_var.get()
        event = None

        try:
            event_data = json.loads(value)
            event = MarketPricePersistedEvent.model_validate(event_data)
            
            logger.info(f"Received new market price for {event.security_id} on {event.price_date}.")

            async for db in get_async_db_session():
                async with db.begin():
                    idempotency_repo = IdempotencyRepository(db)
                    valuation_repo = ValuationRepository(db)
                    reprocessing_repo = InstrumentReprocessingStateRepository(db)
                    
                    if await idempotency_repo.is_event_processed(event_id, SERVICE_NAME):
                        logger.warning(f"Event {event_id} already processed by {SERVICE_NAME}. Skipping.")
                        return
                    
                    latest_business_date = await valuation_repo.get_latest_business_date()
                    is_backdated = latest_business_date and event.price_date < latest_business_date

                    if is_backdated:
                        logger.warning(
                            "Back-dated price event detected. Flagging instrument for reprocessing.",
                            extra={"security_id": event.security_id, "price_date": event.price_date}
                        )
                        await reprocessing_repo.upsert_state(
                            security_id=event.security_id,
                            price_date=event.price_date
                        )
                    
                    await idempotency_repo.mark_event_processed(event_id, "N/A", SERVICE_NAME, correlation_id)

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"Message validation failed for key '{key}'. Sending to DLQ.", exc_info=True)
            await self._send_to_dlq_async(msg, e)
        except (DBAPIError, OperationalError) as e:
            logger.warning(f"Database error while processing price event for {getattr(event, 'security_id', 'Unknown')}: {e}. Retrying...", exc_info=False)
            raise
        except Exception as e:
            logger.error(f"Unexpected error processing message with key '{key}'. Sending to DLQ.", exc_info=True)
            await self._send_to_dlq_async(msg, e)