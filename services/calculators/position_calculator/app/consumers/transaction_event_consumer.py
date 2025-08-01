# services/calculators/position_calculator/app/consumers/transaction_event_consumer.py
import logging
import json
from pydantic import ValidationError

from confluent_kafka import Message
from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.events import TransactionEvent, PositionHistoryPersistedEvent
from portfolio_common.db import get_db_session
from portfolio_common.kafka_utils import get_kafka_producer
from portfolio_common.config import KAFKA_POSITION_HISTORY_PERSISTED_TOPIC # CORRECTED TYPO
from portfolio_common.idempotency_repository import IdempotencyRepository

from ..repositories.position_repository import PositionRepository
from ..core.position_logic import PositionCalculator

logger = logging.getLogger(__name__)

SERVICE_NAME = "position-calculator"

class TransactionEventConsumer(BaseConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._producer = get_kafka_producer()

    async def process_message(self, msg: Message):
        key = msg.key().decode('utf-8') if msg.key() else "NoKey"
        event_id = f"{msg.topic()}-{msg.partition()}-{msg.offset()}"
        new_positions = []

        try:
            event_data = json.loads(msg.value().decode('utf-8'))
            event = TransactionEvent.model_validate(event_data)
        except (ValidationError, json.JSONDecodeError) as e:
            logger.error(f"Validation error for event {event_id}: {e}", exc_info=True)
            await self._send_to_dlq(msg, e)
            return

        with next(get_db_session()) as db:
            try:
                # Atomically check, calculate, and mark as processed
                with db.begin():
                    idempotency_repo = IdempotencyRepository(db)
                    if idempotency_repo.is_event_processed(event_id, SERVICE_NAME):
                        logger.warning(f"Event {event_id} already processed. Skipping.")
                        return

                    position_repo = PositionRepository(db)
                    new_positions = PositionCalculator.calculate(event, db, repo=position_repo)

                    idempotency_repo.mark_event_processed(event_id, event.portfolio_id, SERVICE_NAME)
                
                # The transaction is now committed.
                # Refresh objects to get DB-assigned IDs before publishing.
                for pos in new_positions:
                    db.refresh(pos)

            except Exception as e:
                logger.error(f"Failed during DB transaction for event {event_id}: {e}", exc_info=True)
                # Let the BaseConsumer handle potential DLQ logic for unexpected errors
                await self._send_to_dlq(msg, e)
                return

        # Publish events only after the transaction is successfully committed
        if new_positions:
            for record in new_positions:
                self._publish_persisted_event(record)
            self._producer.flush(timeout=5)
            logger.info(f"[{event.transaction_id}] Published {len(new_positions)} PositionHistoryPersistedEvents.")

    def _publish_persisted_event(self, record: PositionHistoryPersistedEvent):
        try:
            event = PositionHistoryPersistedEvent.model_validate(record)
            self._producer.publish_message(
                topic=KAFKA_POSITION_HISTORY_PERSISTED_TOPIC,
                key=event.security_id,
                value=event.model_dump(mode='json', by_alias=True)
            )
        except Exception as e:
            logger.error(f"[{record.transaction_id}] Failed to publish PositionHistoryPersistedEvent: {e}", exc_info=True)