# services/calculators/position_calculator/app/consumers/transaction_event_consumer.py
import logging
import json
import asyncio
from pydantic import ValidationError
from typing import Optional

from confluent_kafka import Message
from sqlalchemy.exc import IntegrityError
from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.events import TransactionEvent, PositionHistoryPersistedEvent
from portfolio_common.db import get_db_session
from portfolio_common.config import KAFKA_POSITION_HISTORY_PERSISTED_TOPIC
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.outbox_repository import OutboxRepository
from portfolio_common.database_models import PositionHistory

from ..repositories.position_repository import PositionRepository
from ..core.position_logic import PositionCalculator

logger = logging.getLogger(__name__)

SERVICE_NAME = "position-calculator"

class TransactionEventConsumer(BaseConsumer):

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
                outbox_repo = OutboxRepository()
                with db.begin():
                    idempotency_repo = IdempotencyRepository(db)
                
                    if idempotency_repo.is_event_processed(event_id, SERVICE_NAME):
                        logger.warning(f"Event {event_id} already processed. Skipping.")
                        return

                    position_repo = PositionRepository(db)
                    new_positions = PositionCalculator.calculate(event, db, repo=position_repo)

                    # --- NEW: Flush the session to persist records and generate their IDs ---
                    db.flush()

                    # Stage outbox events for each new/updated position history record
                    for record in new_positions:
                        completion_event = PositionHistoryPersistedEvent.model_validate(record)
                        outbox_repo.create_outbox_event(
                            db_session=db,
                            aggregate_type='PositionHistory',
                            aggregate_id=str(record.id),
                            event_type='PositionHistoryPersisted',
                            topic=KAFKA_POSITION_HISTORY_PERSISTED_TOPIC,
                            payload=completion_event.model_dump(mode='json', by_alias=True),
                            correlation_id=correlation_id
                        )

                    idempotency_repo.mark_event_processed(event_id, event.portfolio_id, SERVICE_NAME, correlation_id)
                
                logger.info(f"Successfully processed and saved {len(new_positions)} position records.")
        except IntegrityError as e:
            logger.warning(f"Caught IntegrityError for transaction {getattr(event, 'transaction_id', 'UNKNOWN')}. This should not happen in position-calculator. Sending to DLQ.")
            self._send_to_dlq_sync(msg, e, loop)
        except Exception as e:
            logger.error(f"Unexpected failure during processing for event {event_id}: {e}. Sending to DLQ.", exc_info=True)
            self._send_to_dlq_sync(msg, e, loop)