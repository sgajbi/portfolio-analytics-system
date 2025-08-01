# services/persistence_service/app/consumers/portfolio_consumer.py
import logging
import json
from pydantic import ValidationError
from confluent_kafka import Message

from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.events import PortfolioEvent
from portfolio_common.db import get_db_session
from ..repositories.portfolio_repository import PortfolioRepository

logger = logging.getLogger(__name__)

class PortfolioConsumer(BaseConsumer):
    """
    A concrete consumer for validating and persisting portfolio events.
    """
    async def process_message(self, msg: Message):
        """
        Processes a single portfolio message from Kafka.
        """
        key = msg.key().decode('utf-8') if msg.key() else "NoKey"
        value = msg.value().decode('utf-8')

        try:
            portfolio_data = json.loads(value)
            event = PortfolioEvent.model_validate(portfolio_data)
            logger.info("Successfully validated event", extra={"portfolio_id": event.portfolio_id})

            with next(get_db_session()) as db:
                repo = PortfolioRepository(db)
                repo.create_or_update_portfolio(event)

            logger.info("Successfully persisted", extra={"portfolio_id": event.portfolio_id})

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error("Message validation failed. Sending to DLQ.", extra={"key": key}, exc_info=True)
            await self._send_to_dlq(msg, e)
        except Exception as e:
            logger.error("Unexpected error processing message. Sending to DLQ.", extra={"key": key}, exc_info=True)
            await self._send_to_dlq(msg, e)