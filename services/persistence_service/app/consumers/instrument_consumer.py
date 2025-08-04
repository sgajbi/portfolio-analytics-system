# services/persistence_service/app/consumers/instrument_consumer.py
import logging
import json
import asyncio
from pydantic import ValidationError
from confluent_kafka import Message
from sqlalchemy.exc import IntegrityError
from tenacity import retry, stop_after_attempt, wait_fixed, before_log

from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.events import InstrumentEvent
from portfolio_common.db import get_db_session
from ..repositories.instrument_repository import InstrumentRepository

logger = logging.getLogger(__name__)

class InstrumentConsumer(BaseConsumer):
    """
    A concrete consumer for validating and persisting instrument events.
    Retries on IntegrityError to handle race conditions where related
    entities might not exist yet.
    """
    def process_message(self, msg: Message, loop: asyncio.AbstractEventLoop):
        """Wrapper to call the retryable logic."""
        self._process_message_with_retry(msg, loop)

    @retry(wait=wait_fixed(2), stop=stop_after_attempt(3))
    def _process_message_with_retry(self, msg: Message, loop: asyncio.AbstractEventLoop):
        key = msg.key().decode('utf-8') if msg.key() else "NoKey"
        value = msg.value().decode('utf-8')
        event = None
        
        try:
            instrument_data = json.loads(value)
            event = InstrumentEvent.model_validate(instrument_data)
            logger.info("Successfully validated event", extra={"security_id": event.security_id})

            with next(get_db_session()) as db:
                # FIX: Wrap the operation in a transaction block to ensure commit/rollback.
                with db.begin():
                    repo = InstrumentRepository(db)
                    repo.create_or_update_instrument(event)
            
            logger.info("Successfully persisted", extra={"security_id": event.security_id})

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error("Message validation failed. Sending to DLQ.", extra={"key": key}, exc_info=True)
            self._send_to_dlq_sync(msg, e, loop)
        except IntegrityError:
            logger.warning(f"Caught IntegrityError for instrument {getattr(event, 'security_id', 'UNKNOWN')}. Will retry...")
            raise
        except Exception as e:
            logger.error(f"Unexpected error for instrument {getattr(event, 'security_id', 'UNKNOWN')}. Sending to DLQ.", extra={"key": key}, exc_info=True)
            self._send_to_dlq_sync(msg, e, loop)