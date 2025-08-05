# services/persistence_service/app/consumers/instrument_consumer.py
import logging
import json
import asyncio
from pydantic import ValidationError
from confluent_kafka import Message
from sqlalchemy.exc import IntegrityError
from tenacity import retry, stop_after_attempt, wait_exponential, before_log

from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.events import InstrumentEvent
from portfolio_common.db import get_db_session
from ..repositories.instrument_repository import InstrumentRepository
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.logging_utils import correlation_id_var

logger = logging.getLogger(__name__)

SERVICE_NAME = "persistence-instruments"

class InstrumentConsumer(BaseConsumer):
    """
    A concrete consumer for validating and persisting instrument events idempotently.
    Retries on IntegrityError to handle race conditions where related
    entities might not exist yet.
    """
    def process_message(self, msg: Message, loop: asyncio.AbstractEventLoop):
        """Wrapper to call the retryable logic."""
        self._process_message_with_retry(msg, loop)

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10), 
        stop=stop_after_attempt(3), 
        before=before_log(logger, logging.INFO),
        reraise=True
    )
    def _process_message_with_retry(self, msg: Message, loop: asyncio.AbstractEventLoop):
        key = msg.key().decode('utf-8') if msg.key() else "NoKey"
        value = msg.value().decode('utf-8')
        correlation_id = correlation_id_var.get()
        event = None

        event_id = f"{msg.topic()}-{msg.partition()}-{msg.offset()}"
        
        try:
            instrument_data = json.loads(value)
            event = InstrumentEvent.model_validate(instrument_data)
            logger.info("Successfully validated event", 
                extra={"security_id": event.security_id, "event_id": event_id})

            with next(get_db_session()) as db:
                with db.begin():
                    repo = InstrumentRepository(db)
                    idempotency_repo = IdempotencyRepository(db)

                    if idempotency_repo.is_event_processed(event_id, SERVICE_NAME):
                        logger.warning(
                            "Event has already been processed. Skipping.",
                            extra={"event_id": event_id, "service_name": SERVICE_NAME}
                        )
                        return

                    repo.create_or_update_instrument(event)

                    idempotency_repo.mark_event_processed(
                        event_id=event_id,
                        portfolio_id="N/A", 
                        service_name=SERVICE_NAME,
                        correlation_id=correlation_id
                    )
            
            logger.info("Successfully persisted instrument and marked event as processed", 
                extra={"security_id": event.security_id, "event_id": event_id})

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error("Message validation failed. Sending to DLQ.", 
                extra={"key": key, "event_id": event_id}, exc_info=True)
            self._send_to_dlq_sync(msg, e, loop)
        except IntegrityError:
            logger.warning(f"Caught IntegrityError for instrument {getattr(event, 'security_id', 'UNKNOWN')}. Will retry...",
                extra={"event_id": event_id})
            raise
        except Exception as e:
            logger.error(f"Unexpected error for instrument {getattr(event, 'security_id', 'UNKNOWN')}. Sending to DLQ.", 
                extra={"key": key, "event_id": event_id}, exc_info=True)
            self._send_to_dlq_sync(msg, e, loop)