import logging
import json
from pydantic import ValidationError
from decimal import Decimal

from confluent_kafka import Message
from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.events import TransactionEvent, PositionHistoryPersistedEvent
from portfolio_common.db import get_db_session
from portfolio_common.database_models import PositionHistory, Transaction
from portfolio_common.kafka_utils import get_kafka_producer
from portfolio_common.config import KAFKA_POSITION_HISTORY_PERSISTED_TOPIC
from ..repositories.position_repository import PositionRepository
from ..core.position_logic import PositionCalculator
from ..core.position_models import PositionState

logger = logging.getLogger(__name__)

class TransactionEventConsumer(BaseConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._producer = get_kafka_producer()

    async def process_message(self, msg: Message):
        key = msg.key().decode('utf-8') if msg.key() else "NoKey"
        value = msg.value().decode('utf-8')

        try:
            event_data = json.loads(value)
            incoming_event = TransactionEvent.model_validate(event_data)
            
            logger.info(f"Processing transaction {incoming_event.transaction_id} dated {incoming_event.transaction_date}")
            self._recalculate_position_history(incoming_event)

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"Message validation failed for key '{key}': {e}. Value: '{value}'")
            await self._send_to_dlq(msg, e)
        except Exception as e:
            logger.error(f"Unexpected error processing message with key '{key}': {e}", exc_info=True)
            await self._send_to_dlq(msg, e)

    def _recalculate_position_history(self, incoming_event: TransactionEvent):
        with next(get_db_session()) as db:
            try:
                repo = PositionRepository(db)
                transaction_date_only = incoming_event.transaction_date.date()
                
                anchor_position = repo.get_last_position_before(
                    portfolio_id=incoming_event.portfolio_id,
                    security_id=incoming_event.security_id,
                    a_date=transaction_date_only
                )
                current_state = PositionState(
                    quantity=anchor_position.quantity if anchor_position else Decimal(0),
                    cost_basis=anchor_position.cost_basis if anchor_position else Decimal(0)
                )

                db_txns = repo.get_transactions_on_or_after(
                    portfolio_id=incoming_event.portfolio_id,
                    security_id=incoming_event.security_id,
                    a_date=transaction_date_only
                )

                txns_to_replay_map = {t.transaction_id: t for t in db_txns}
                incoming_txn_obj = Transaction(**incoming_event.model_dump())
                txns_to_replay_map[incoming_event.transaction_id] = incoming_txn_obj
                
                txns_to_replay = sorted(txns_to_replay_map.values(), key=lambda t: t.transaction_date)

                if not txns_to_replay:
                    return

                # This is now a critical step that must happen before inserting new records
                with db.begin():
                    repo.delete_positions_from(
                        portfolio_id=incoming_event.portfolio_id,
                        security_id=incoming_event.security_id,
                        a_date=transaction_date_only
                    )

                # --- DEFINITIVE FIX: Insert and publish one-by-one ---
                for txn in txns_to_replay:
                    with db.begin(): # Each record in its own transaction for clarity
                        txn_event = TransactionEvent.model_validate(txn)
                        current_state = PositionCalculator.calculate_next_position(current_state, txn_event)
                        
                        new_record = PositionHistory(
                            portfolio_id=txn.portfolio_id,
                            security_id=txn.security_id,
                            transaction_id=txn.transaction_id,
                            position_date=txn.transaction_date.date(),
                            quantity=current_state.quantity,
                            cost_basis=current_state.cost_basis
                        )
                        db.add(new_record)
                        db.flush() # Assigns the ID to new_record
                        db.commit() # Commits the record
                  
                        # Now that the record is committed and has an ID, publish the event
                        self._publish_persisted_event(new_record)

                self._producer.flush(timeout=5)

            except Exception as e:
                logger.error(f"Recalculation failed for transaction {incoming_event.transaction_id}: {e}", exc_info=True)
    
    def _publish_persisted_event(self, record: PositionHistory):
        """Publishes a single, guaranteed-to-be-committed event."""
        if not record or not record.id:
            logger.error("Attempted to publish an invalid or uncommitted record.")
            return
        try:
            event = PositionHistoryPersistedEvent.model_validate(record)
            self._producer.publish_message(
                topic=KAFKA_POSITION_HISTORY_PERSISTED_TOPIC,
                key=event.security_id,
                value=event.model_dump(mode='json', by_alias=True)
            )
            logger.info(f"Successfully published PositionHistoryPersistedEvent for id {record.id}")
        except Exception as e:
            logger.error(f"Failed to publish event for position_history_id {record.id}: {e}", exc_info=True)