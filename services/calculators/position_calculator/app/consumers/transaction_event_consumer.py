# services/calculators/position_calculator/app/consumers/transaction_event_consumer.py
import logging
import json
import asyncio
from pydantic import ValidationError
from typing import Optional

from confluent_kafka import Message
from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.events import TransactionEvent, PositionHistoryPersistedEvent
from portfolio_common.db import get_db_session
from portfolio_common.kafka_utils import get_kafka_producer
from portfolio_common.config import KAFKA_POSITION_HISTORY_PERSISTED_TOPIC
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.database_models import PositionHistory

from ..repositories.position_repository import PositionRepository
from ..core.position_logic import PositionCalculator

logger = logging.getLogger(__name__)

SERVICE_NAME = "position-calculator"

class TransactionEventConsumer(BaseConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._producer = get_kafka_producer()

    def process_message(self, msg: Message, loop: asyncio.AbstractEventLoop):
        key = msg.key().decode('utf-8') if msg.key() else "NoKey"
        event_id = f"{msg.topic()}-{msg.partition()}-{msg.offset()}"
        correlation_id = correlation_id_var.get()
        new_positions = []
        event = None

        try:
            event_data = json.loads(msg.value().decode('utf-8'))
            event = TransactionEvent.model_validate(event_data)
        except (ValidationError, json.JSONDecodeError) as e:
            logger.error(f"Validation error for event {event_id}: {e}. Sending to DLQ.", exc_info=True)
            self._send_to_dlq_sync(msg, e, loop)
            return

        try:
            with next(get_db_session()) as db:
                with db.begin():
                    idempotency_repo = IdempotencyRepository(db)
                
                    if idempotency_repo.is_event_processed(event_id, SERVICE_NAME):
                        logger.warning(f"Event {event_id} already processed. Skipping.")
                        return

                    position_repo = PositionRepository(db)
                    new_positions = PositionCalculator.calculate(event, db, repo=position_repo)
                    idempotency_repo.mark_event_processed(event_id, event.portfolio_id, SERVICE_NAME, correlation_id)
                
                if new_positions:
                    for pos in new_positions:
                        db.refresh(pos)
                    
                    logger.info(f"Successfully processed and saved {len(new_positions)} position records.")
                    
                    for record in new_positions:
                        self._publish_persisted_event(record, correlation_id)
            
                    self._producer.flush(timeout=5)
                    logger.info(f"[{event.transaction_id}] Published {len(new_positions)} PositionHistoryPersistedEvents.")

        except Exception as e:
            logger.error(f"Unexpected failure during processing for event {event_id}: {e}. Sending to DLQ.", exc_info=True)
            self._send_to_dlq_sync(msg, e, loop)
            return

    def _publish_persisted_event(self, record: PositionHistory, correlation_id: Optional[str]):
        try:
            event = PositionHistoryPersistedEvent.model_validate(record)
            headers = [('correlation_id', correlation_id.encode('utf-8'))] if correlation_id else None
            
            self._producer.publish_message(
                topic=KAFKA_POSITION_HISTORY_PERSISTED_TOPIC,
                key=event.security_id,
                value=event.model_dump(mode='json', by_alias=True),
                headers=headers
            )
        except Exception as e:
            logger.error(f"[{record.transaction_id}] Failed to publish PositionHistoryPersistedEvent: {e}", exc_info=True)