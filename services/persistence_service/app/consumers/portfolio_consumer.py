# services/persistence_service/app/consumers/portfolio_consumer.py
import logging
import json
import asyncio
from pydantic import ValidationError
from confluent_kafka import Message
from sqlalchemy.exc import IntegrityError
from tenacity import retry, stop_after_attempt, wait_exponential, before_log

from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.events import PortfolioEvent
from portfolio_common.db import get_db_session
from ..repositories.portfolio_repository import PortfolioRepository
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.logging_utils import correlation_id_var

logger = logging.getLogger(__name__)

SERVICE_NAME = "persistence-portfolios"

class PortfolioConsumer(BaseConsumer):
    """
    A concrete consumer for validating and persisting portfolio events idempotently.
    """
    def process_message(self, msg: Message, loop: asyncio.AbstractEventLoop):
        """
        Processes a single portfolio message from Kafka.
        """
        try:
            self._process_message_with_retry(msg, loop)
        except Exception as e:
            logger.error(f"Fatal error processing portfolio message after retries. Sending to DLQ. Key={msg.key()}", exc_info=True)
            self._send_to_dlq_sync(msg, e, loop)

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
            portfolio_data = json.loads(value)
            event = PortfolioEvent.model_validate(portfolio_data)
            logger.info("Successfully validated event", 
                extra={"portfolio_id": event.portfolio_id, "event_id": event_id})

            with next(get_db_session()) as db:
                with db.begin():
                    repo = PortfolioRepository(db)
                    idempotency_repo = IdempotencyRepository(db)

                    if idempotency_repo.is_event_processed(event_id, SERVICE_NAME):
                        logger.warning(
                            "Event has already been processed. Skipping.",
                            extra={"event_id": event_id, "service_name": SERVICE_NAME}
                        )
                        return

                    repo.create_or_update_portfolio(event)

                    idempotency_repo.mark_event_processed(
                        event_id=event_id,
                        portfolio_id=event.portfolio_id,
                        service_name=SERVICE_NAME,
                        correlation_id=correlation_id
                    )

            logger.info("Successfully persisted portfolio and marked event as processed", 
                extra={"portfolio_id": event.portfolio_id, "event_id": event_id})

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error("Message validation failed. Sending to DLQ.", 
                extra={"key": key, "event_id": event_id}, exc_info=True)
            self._send_to_dlq_sync(msg, e, loop)
        except IntegrityError:
            logger.warning(
                "Caught IntegrityError, likely a race condition. Will retry...",
                extra={"portfolio_id": getattr(event, 'portfolio_id', 'UNKNOWN'), "event_id": event_id},
            )
            raise
        except Exception as e:
            logger.error(f"Unexpected error processing message for portfolio {getattr(event, 'portfolio_id', 'UNKNOWN')}. Sending to DLQ.", 
                extra={"key": key, "event_id": event_id}, exc_info=True)
            self._send_to_dlq_sync(msg, e, loop)