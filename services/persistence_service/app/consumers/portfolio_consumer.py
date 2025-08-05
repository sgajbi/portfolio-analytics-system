# services/persistence_service/app/consumers/portfolio_consumer.py
import logging
import json
import asyncio
from pydantic import ValidationError
from confluent_kafka import Message

from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.events import PortfolioEvent
from portfolio_common.db import get_db_session
from ..repositories.portfolio_repository import PortfolioRepository
from portfolio_common.idempotency_repository import IdempotencyRepository # NEW IMPORT
from portfolio_common.logging_utils import correlation_id_var # NEW IMPORT

logger = logging.getLogger(__name__)

# NEW: Define a constant for the service name.
SERVICE_NAME = "persistence-portfolios"

class PortfolioConsumer(BaseConsumer):
    """
    A concrete consumer for validating and persisting portfolio events idempotently.
    """
    def process_message(self, msg: Message, loop: asyncio.AbstractEventLoop):
        """
        Processes a single portfolio message from Kafka.
        """
        key = msg.key().decode('utf-8') if msg.key() else "NoKey"
        value = msg.value().decode('utf-8')
        correlation_id = correlation_id_var.get()
        event = None

        # NEW: Create a unique, deterministic ID for the event.
        event_id = f"{msg.topic()}-{msg.partition()}-{msg.offset()}"

        try:
            portfolio_data = json.loads(value)
            event = PortfolioEvent.model_validate(portfolio_data)
            logger.info("Successfully validated event", 
                extra={"portfolio_id": event.portfolio_id, "event_id": event_id})

            with next(get_db_session()) as db:
                # This block now explicitly manages the transaction.
                with db.begin():
                    repo = PortfolioRepository(db)
                    idempotency_repo = IdempotencyRepository(db) # NEW

                    # --- IDEMPOTENCY CHECK ---
                    if idempotency_repo.is_event_processed(event_id, SERVICE_NAME):
                        logger.warning(
                            "Event has already been processed. Skipping.",
                            extra={"event_id": event_id, "service_name": SERVICE_NAME}
                        )
                        return

                    repo.create_or_update_portfolio(event)

                    # --- MARK AS PROCESSED ---
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
        except Exception as e:
            logger.error(f"Unexpected error processing message for portfolio {getattr(event, 'portfolio_id', 'UNKNOWN')}. Sending to DLQ.", 
                extra={"key": key, "event_id": event_id}, exc_info=True)
            self._send_to_dlq_sync(msg, e, loop)