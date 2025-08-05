import logging
import json
import asyncio
from typing import Optional
from pydantic import ValidationError
from confluent_kafka import Message
from sqlalchemy.exc import IntegrityError
from tenacity import retry, stop_after_attempt, wait_fixed

from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.events import FxRateEvent
from portfolio_common.db import get_db_session
from ..repositories.fx_rate_repository import FxRateRepository
from portfolio_common.idempotency_repository import IdempotencyRepository # NEW IMPORT
from portfolio_common.logging_utils import correlation_id_var # NEW IMPORT

logger = logging.getLogger(__name__)

# NEW: Define a constant for the service name.
SERVICE_NAME = "persistence-fx-rates"

class FxRateConsumer(BaseConsumer):
    """
    Consumes, validates, and persists FX rate events idempotently with robust error handling and DLQ support.
    """

    def process_message(self, msg: Message, loop: asyncio.AbstractEventLoop):
        """
        Entrypoint for handling an incoming Kafka message.
        """
        try:
            self._process_message_with_retry(msg, loop)
        except Exception as e:
            logger.error(f"Fatal error processing FX rate message. Sending to DLQ. Key={msg.key()}", exc_info=True)
            self._send_to_dlq_sync(msg, e, loop)

    @retry(wait=wait_fixed(2), stop=stop_after_attempt(3), reraise=True)
    def _process_message_with_retry(self, msg: Message, loop: asyncio.AbstractEventLoop):
        key = msg.key().decode('utf-8') if msg.key() else "NoKey"
        value = msg.value().decode('utf-8')
        correlation_id = correlation_id_var.get()
        event = None

        # NEW: Create a unique, deterministic ID for the event.
        event_id = f"{msg.topic()}-{msg.partition()}-{msg.offset()}"

        try:
            fx_rate_data = json.loads(value)
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode failed for FX rate event. Key={key} Error={e}. Sending to DLQ.", 
                extra={"event_id": event_id}, exc_info=True)
            self._send_to_dlq_sync(msg, e, loop)
            return

        try:
            event = FxRateEvent.model_validate(fx_rate_data)
        except ValidationError as e:
            logger.error(f"Validation failed for FX rate event. Key={key} Error={e}. Sending to DLQ.", 
                extra={"event_id": event_id}, exc_info=True)
            self._send_to_dlq_sync(msg, e, loop)
            return

        logger.info(
            f"Received FX rate event: {event.from_currency}->{event.to_currency} on {event.rate_date}",
            extra={"event_id": event_id}
        )

        try:
            with next(get_db_session()) as db:
                with db.begin():
                    repo = FxRateRepository(db)
                    idempotency_repo = IdempotencyRepository(db) # NEW

                    # --- IDEMPOTENCY CHECK ---
                    if idempotency_repo.is_event_processed(event_id, SERVICE_NAME):
                        logger.warning(
                            "Event has already been processed. Skipping.",
                            extra={"event_id": event_id, "service_name": SERVICE_NAME}
                        )
                        return

                    _, status = repo.upsert_fx_rate(event)

                    # --- MARK AS PROCESSED ---
                    idempotency_repo.mark_event_processed(
                        event_id=event_id,
                        portfolio_id="N/A", # FX rates are not portfolio-specific
                        service_name=SERVICE_NAME,
                        correlation_id=correlation_id
                    )

                    logger.info(
                        f"FX Rate event processed: {event.from_currency}->{event.to_currency} on {event.rate_date} "
                        f"Status={status}", extra={"event_id": event_id}
                    )
        except IntegrityError as e:
            logger.warning(
                f"IntegrityError (likely duplicate) for FX rate: {event.from_currency}->{event.to_currency} "
                f"on {event.rate_date}. Key={key}. Error={e}. Sending to DLQ.",
                extra={"event_id": event_id}
            )
            self._send_to_dlq_sync(msg, e, loop)
        except Exception as e:
            logger.error(
                f"Unexpected error for FX rate event: {event.from_currency}->{event.to_currency} "
                f"on {event.rate_date}. Key={key}. Sending to DLQ.",
                extra={"event_id": event_id},
                exc_info=True
            )
            self._send_to_dlq_sync(msg, e, loop)