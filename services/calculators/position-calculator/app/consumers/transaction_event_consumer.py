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
    """
    Consumes enriched transaction events, recalculates position history,
    and publishes an event for each persisted position record.
    """
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
        except Exception as e:
            logger.error(f"Unexpected error processing message with key '{key}': {e}", exc_info=True)

    def _recalculate_position_history(self, incoming_event: TransactionEvent):
        """
        Executes the 'wipe and replay' strategy for a given security and
        publishes events for newly created position history records.
        """
        new_history_records = []
        with next(get_db_session()) as db:
            try:
                repo = PositionRepository(db)
                transaction_date_only = incoming_event.transaction_date.date()
                
                with db.begin_nested():
                    anchor_position = repo.get_last_position_before(
                        portfolio_id=incoming_event.portfolio_id,
                        security_id=incoming_event.security_id,
                        a_date=transaction_date_only
                    )
                    current_state = PositionState(
                        quantity=anchor_position.quantity if anchor_position else Decimal(0),
                        cost_basis=anchor_position.cost_basis if anchor_position else Decimal(0)
                    )

                    subsequent_txns = repo.get_transactions_on_or_after(
                        portfolio_id=incoming_event.portfolio_id,
                        security_id=incoming_event.security_id,
                        a_date=transaction_date_only
                    )

                    repo.delete_positions_from(
                        portfolio_id=incoming_event.portfolio_id,
                        security_id=incoming_event.security_id,
                        a_date=transaction_date_only
                    )

                    txns_to_replay = sorted(subsequent_txns, key=lambda t: (t.transaction_date, t.id))

                    if not txns_to_replay:
                        logger.warning(f"No transactions to replay for {incoming_event.security_id} on or after {transaction_date_only}")
                        return

                    for txn in txns_to_replay:
                        txn_event = TransactionEvent.model_validate(txn)
                        current_state = PositionCalculator.calculate_next_position(current_state, txn_event)
                        
                        new_history_records.append(
                            PositionHistory(
                                portfolio_id=txn.portfolio_id,
                                security_id=txn.security_id,
                                transaction_id=txn.transaction_id,
                                position_date=txn.transaction_date.date(), # <-- CORRECTED: Use .date()
                                quantity=current_state.quantity,
                                cost_basis=current_state.cost_basis
                            )
                        )
                    
                    if new_history_records:
                        repo.save_positions(new_history_records)
                
                logger.info(f"Successfully reprocessed and saved {len(new_history_records)} positions for {incoming_event.security_id}")

                self._publish_persisted_events(new_history_records)
                self._producer.flush(timeout=5)

            except Exception as e:
                logger.error(f"Recalculation failed for transaction {incoming_event.transaction_id}: {e}", exc_info=True)
    
    def _publish_persisted_events(self, records: list[PositionHistory]):
        """Publishes PositionHistoryPersistedEvent for each record."""
        if not records:
            return

        count = 0
        for record in records:
            try:
                event = PositionHistoryPersistedEvent.model_validate(record)
                self._producer.publish_message(
                    topic=KAFKA_POSITION_HISTORY_PERSISTED_TOPIC,
                    key=event.security_id,
                    value=event.model_dump(mode='json')
                )
                count += 1
            except Exception as e:
                logger.error(f"Failed to publish PositionHistoryPersistedEvent for position_history_id {record.id}: {e}", exc_info=True)
        
        if count > 0:
            logger.info(f"Successfully published {count} PositionHistoryPersistedEvent messages.")