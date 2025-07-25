import logging
import json
from pydantic import ValidationError
from decimal import Decimal

from confluent_kafka import Message
from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.events import TransactionEvent
from portfolio_common.db import get_db_session
from portfolio_common.database_models import PositionHistory, Transaction
from ..repositories.position_repository import PositionRepository
from ..core.position_logic import PositionCalculator
from ..core.position_models import PositionState

logger = logging.getLogger(__name__)

class TransactionEventConsumer(BaseConsumer):
    """
    Consumes enriched transaction events and orchestrates the position calculation
    and history recalculation logic.
    """

    async def process_message(self, msg: Message):
        key = msg.key().decode('utf-8') if msg.key() else "NoKey"
        value = msg.value().decode('utf-8')

        try:
            event_data = json.loads(value)
            # We need to map the incoming event to our shared TransactionEvent model
            # and our DB Transaction model for processing.
            incoming_event = TransactionEvent.model_validate(event_data)
            db_transaction = Transaction(**incoming_event.model_dump())
            
            logger.info(f"Processing transaction {incoming_event.transaction_id} dated {incoming_event.transaction_date}")
            self._recalculate_position_history(db_transaction)

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"Message validation failed for key '{key}': {e}. Value: '{value}'")
        except Exception as e:
            logger.error(f"Unexpected error processing message with key '{key}': {e}", exc_info=True)

    def _recalculate_position_history(self, incoming_txn: Transaction):
        """
        Executes the 'wipe and replay' strategy for a given security.
        """
        with next(get_db_session()) as db:
            try:
                with db.begin(): # Manages the transaction (commit/rollback)
                    repo = PositionRepository(db)

                    # 1. Find anchor point
                    anchor_position = repo.get_last_position_before(
                        portfolio_id=incoming_txn.portfolio_id,
                        security_id=incoming_txn.security_id,
                        a_date=incoming_txn.transaction_date.date()
                    )
                    current_state = PositionState(
                        quantity=anchor_position.quantity if anchor_position else Decimal(0),
                        cost_basis=anchor_position.cost_basis if anchor_position else Decimal(0)
                    )

                    # 2. Gather subsequent transactions
                    subsequent_txns = repo.get_transactions_on_or_after(
                        portfolio_id=incoming_txn.portfolio_id,
                        security_id=incoming_txn.security_id,
                        a_date=incoming_txn.transaction_date.date()
                    )

                    # 3. Clear affected history
                    repo.delete_positions_from(
                        portfolio_id=incoming_txn.portfolio_id,
                        security_id=incoming_txn.security_id,
                        a_date=incoming_txn.transaction_date.date()
                    )

                    # 4. Sort and recalculate
                    # We use the DB Transaction model here as it has all necessary fields
                    txns_to_replay = sorted(subsequent_txns, key=lambda t: (t.transaction_date, t.id))

                    new_history_records = []
                    for txn in txns_to_replay:
                        # Convert DB model to Pydantic event model for the calculator
                        txn_event = TransactionEvent.model_validate(txn)
                        current_state = PositionCalculator.calculate_next_position(current_state, txn_event)
                        
                        new_history_records.append(
                            PositionHistory(
                                portfolio_id=txn.portfolio_id,
                                security_id=txn.security_id,
                                transaction_id=txn.transaction_id,
                                position_date=txn.transaction_date.date(),
                                quantity=current_state.quantity,
                                cost_basis=current_state.cost_basis
                            )
                        )
                    
                    # 5. Save the new history
                    repo.save_positions(new_history_records)
                
                logger.info(f"Successfully reprocessed {len(new_history_records)} positions for {incoming_txn.security_id}")

            except Exception as e:
                logger.error(f"Recalculation failed for transaction {incoming_txn.transaction_id}: {e}", exc_info=True)
                # The 'with db.begin()' context manager will automatically roll back