# src/services/persistence_service/app/consumers/fx_rate_consumer.py
import logging
import json
import asyncio
from typing import Optional
from pydantic import ValidationError
from confluent_kafka import Message
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError
from tenacity import retry, stop_after_delay, wait_exponential, before_log, retry_if_exception_type

from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.events import FxRateEvent
from portfolio_common.db import get_async_db_session
from ..repositories.fx_rate_repository import FxRateRepository
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.logging_utils import correlation_id_var

logger = logging.getLogger(__name__)

SERVICE_NAME = "persistence-fx-rates"

class FxRateConsumer(BaseConsumer):
    """
    Consumes, validates, and persists FX rate events idempotently with robust error handling and DLQ support.
    """
    async def process_message(self, msg: Message):
        """
        Entrypoint for handling an incoming Kafka message.
        """
        try:
            await self._process_message_with_retry(msg)
        except Exception as e:
            logger.error(f"Fatal error processing FX rate message. Sending to DLQ. Key={msg.key()}", exc_info=True)
            await self._send_to_dlq_async(msg, e)

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_delay(90),
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

        try:
            fx_rate_data = json.loads(value)
            event = FxRateEvent.model_validate(fx_rate_data)
        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"Validation or JSON decode failed for FX rate event. Key={key}. Sending to DLQ.", 
                extra={"event_id": event_id}, exc_info=True)
            await self._send_to_dlq_async(msg, e)
            return

        logger.info(
            f"Received FX rate event: {event.from_currency}->{event.to_currency} on {event.rate_date}",
            extra={"event_id": event_id}
        )
        
        try:
            async for db in get_async_db_session():
                async with db.begin():
                    repo = FxRateRepository(db)
                    idempotency_repo = IdempotencyRepository(db)

                    if await idempotency_repo.is_event_processed(event_id, SERVICE_NAME):
                        logger.warning(
                            "Event has already been processed. Skipping.",
                            extra={"event_id": event_id, "service_name": SERVICE_NAME}
                        )
                        return

                    _, status = await repo.upsert_fx_rate(event)

                    await idempotency_repo.mark_event_processed(
                        event_id=event_id,
                        portfolio_id="N/A",
                        service_name=SERVICE_NAME,
                        correlation_id=correlation_id
                    )

                    logger.info(
                        f"FX Rate event processed: {event.from_currency}->{event.to_currency} on {event.rate_date} "
                        f"Status={status}", extra={"event_id": event_id}
                    )
        except (DBAPIError, IntegrityError, OperationalError):
            logger.warning(
                f"Caught a DB error for FX rate: {getattr(event, 'from_currency', 'UNK')}->{getattr(event, 'to_currency', 'UNK')} "
                f"on {getattr(event, 'rate_date', 'UNKNOWN')}. Will retry...",
                extra={"event_id": event_id}
            )
            raise
        except Exception as e:
            logger.error(
                f"Unexpected error for FX rate event: {getattr(event, 'from_currency', 'UNK')}->{getattr(event, 'to_currency', 'UNK')} "
                f"on {getattr(event, 'rate_date', 'UNKNOWN')}. Sending to DLQ.",
                extra={"event_id": event_id},
                exc_info=True
            )
            await self._send_to_dlq_async(msg, e)