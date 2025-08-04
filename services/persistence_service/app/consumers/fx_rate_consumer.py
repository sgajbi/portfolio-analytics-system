# services/persistence_service/app/consumers/fx_rate_consumer.py
import logging
import json
import asyncio
from pydantic import ValidationError
from confluent_kafka import Message
from sqlalchemy.exc import IntegrityError
from tenacity import retry, stop_after_attempt, wait_fixed

from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.events import FxRateEvent
from portfolio_common.db import get_db_session
from ..repositories.fx_rate_repository import FxRateRepository

logger = logging.getLogger(__name__)

class FxRateConsumer(BaseConsumer):
    """
    A concrete consumer for validating and persisting FX rate events.
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
            fx_rate_data = json.loads(value)
            event = FxRateEvent.model_validate(fx_rate_data)
            logger.info(
                "Successfully validated event for FX rate", 
                extra={
                    "from_currency": event.from_currency,
                    "to_currency": event.to_currency,
                    "rate_date": event.rate_date
                }
            )

            with next(get_db_session()) as db:
                with db.begin():
                    repo = FxRateRepository(db)
                    repo.create_fx_rate(event)
            
        except (json.JSONDecodeError, ValidationError) as e:
            logger.error("Message validation failed. Sending to DLQ.", extra={"key": key}, exc_info=True)
            self._send_to_dlq_sync(msg, e, loop)
        except IntegrityError:
            logger.warning(f"Caught IntegrityError for fx_rate. Will retry...")
            raise
        except Exception as e:
            logger.error(f"Unexpected error for fx_rate. Sending to DLQ.", extra={"key": key}, exc_info=True)
            self._send_to_dlq_sync(msg, e, loop)