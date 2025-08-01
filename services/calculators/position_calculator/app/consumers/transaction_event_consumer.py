import logging
import json
from pydantic import ValidationError
from decimal import Decimal

from portfolio_common.database_models import PositionHistory

from confluent_kafka import Message
from sqlalchemy.orm import Session
from sqlalchemy import text
from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.events import TransactionEvent
from portfolio_common.db import get_db_session
from portfolio_common.database_models import ProcessedEvent
from portfolio_common.kafka_utils import get_kafka_producer
from portfolio_common.config import KAFKA_POSITION_HISTORY_PERSISTED_TOPIC
from ..repositories.position_repository import PositionRepository
from ..core.position_logic import PositionCalculator

logger = logging.getLogger(__name__)

class TransactionEventConsumer(BaseConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._producer = get_kafka_producer()

    async def process_message(self, msg: Message):
        key = msg.key().decode('utf-8') if msg.key() else "NoKey"
        event_id = f"{key}_{msg.timestamp()[1]}"  

        try:
            event_data = json.loads(msg.value().decode('utf-8'))
            event = TransactionEvent(**event_data)
        except ValidationError as e:
            logger.error(f"[Validation Error] {e}")
            return
        except json.JSONDecodeError as e:
            logger.error(f"[JSON Decode Error] {e}")
            return

        with get_db_session() as db_session:
            exists = db_session.query(ProcessedEvent).filter_by(event_id=event_id).first()
            if exists:
                logger.info(f"[Idempotent Skip] Event {event_id} already processed for portfolio {event.portfolio_id}")
                return
            
            PositionCalculator.calculate(event, db_session)

            processed_event = ProcessedEvent(
                event_id=event_id,
                portfolio_id=event.portfolio_id,
                service_name="position-calculator"
            )
            db_session.add(processed_event)
            db_session.commit()
            logger.info(f"[Processed] Event {event_id} stored in processed_events")


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

                txns_to_replay = sorted(db_txns, key=lambda t: t.transaction_date)

                if not txns_to_replay:
                    logger.info(f"No transactions to replay for {incoming_event.transaction_id}")
                    return

                repo.delete_positions_from(
                    portfolio_id=incoming_event.portfolio_id,
                    security_id=incoming_event.security_id,
                    a_date=transaction_date_only
                )

                new_records = []
                for txn in txns_to_replay:
                    txn_event = TransactionEvent.model_validate(txn)
                    current_state = PositionCalculator.calculate_next_position(current_state, txn_event)

                    new_records.append(PositionHistory(
                        portfolio_id=txn.portfolio_id,
                        security_id=txn.security_id,
                        transaction_id=txn.transaction_id,
                        position_date=txn.transaction_date.date(),
                        quantity=current_state.quantity,
                        cost_basis=current_state.cost_basis
                    ))

                if new_records:
                    repo.save_positions(new_records)
                    db.commit()  # ✅ Commit before publish

                    for record in new_records:
                        self._publish_persisted_event(record)

                    self._producer.flush(timeout=5)
                    logger.info(f"[{incoming_event.transaction_id}] Published {len(new_records)} PositionHistoryPersistedEvents.")

            except Exception as e:
                db.rollback()
                logger.error(f"Recalculation failed for transaction {incoming_event.transaction_id}: {e}", exc_info=True)

    def _publish_persisted_event(self, record: PositionHistory):
        try:
            event = PositionHistoryPersistedEvent.model_validate(record)
            self._producer.publish_message(
                topic=KAFKA_POSITION_HISTORY_PERSISTED_TOPIC,
                key=event.security_id or getattr(record, "security_id", "Unknown"),
                value=event.model_dump(mode='json', by_alias=True)
            )
            logger.debug(f"[{record.transaction_id}] Published PositionHistoryPersistedEvent (ID={getattr(record,'id','NA')})")
        except Exception as e:
            logger.error(f"[{record.transaction_id}] Failed to publish event: {e}", exc_info=True)
