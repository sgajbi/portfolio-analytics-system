import logging
import json
import time
from pydantic import ValidationError
from decimal import Decimal
from confluent_kafka import Message
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError
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
        key = msg.key().decode("utf-8") if msg.key() else "NoKey"
        value = msg.value().decode("utf-8")

        try:
            event_data = json.loads(value)
            incoming_event = TransactionEvent.model_validate(event_data)
            self._recalculate_position_history(incoming_event)

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"[{key}] Validation failed: {e} | Payload: {value}")
            await self._send_to_dlq(msg, e)

        except Exception as e:
            logger.error(f"[{key}] Unexpected error: {e}", exc_info=True)
            await self._send_to_dlq(msg, e)

    def _recalculate_position_history(self, incoming_event: TransactionEvent):
        retry_attempts = 3
        backoff = 2

        for attempt in range(retry_attempts):
            try:
                with next(get_db_session()) as db:
                    self._process_recalculation(db, incoming_event)
                break  # success, exit retry loop

            except OperationalError as oe:
                logger.warning(
                    f"[{incoming_event.transaction_id}] DB operational error: {oe}, retry {attempt+1}/{retry_attempts}"
                )
                time.sleep(backoff ** attempt)
            except Exception as e:
                logger.error(
                    f"[{incoming_event.transaction_id}] Recalculation failed: {e}",
                    exc_info=True
                )
                break  # fail fast for non-transient error

    def _process_recalculation(self, db: Session, incoming_event: TransactionEvent):
        repo = PositionRepository(db)
        txn_date_only = incoming_event.transaction_date.date()

        # Optional advisory lock for concurrency safety
        # (This can be a DB-level lock or a distributed lock)
        lock_key = f"{incoming_event.portfolio_id}:{incoming_event.security_id}"
        logger.debug(f"Acquiring lock for {lock_key}...")
        # lock_acquire(lock_key)  # <-- Hook for future distributed lock

        anchor_position = repo.get_last_position_before(
            portfolio_id=incoming_event.portfolio_id,
            security_id=incoming_event.security_id,
            a_date=txn_date_only
        )

        current_state = PositionState(
            quantity=anchor_position.quantity if anchor_position else Decimal(0),
            cost_basis=anchor_position.cost_basis if anchor_position else Decimal(0)
        )

        db_txns = repo.get_transactions_on_or_after(
            portfolio_id=incoming_event.portfolio_id,
            security_id=incoming_event.security_id,
            a_date=txn_date_only
        )

        txns_to_replay = sorted(db_txns, key=lambda t: t.transaction_date)

        if not txns_to_replay:
            logger.debug(f"[{incoming_event.transaction_id}] No transactions to replay.")
            return

        repo.delete_positions_from(
            portfolio_id=incoming_event.portfolio_id,
            security_id=incoming_event.security_id,
            a_date=txn_date_only
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
            db.commit()

            committed_ids = [rec.transaction_id for rec in new_records]
            persisted = db.query(PositionHistory).filter(
                PositionHistory.transaction_id.in_(committed_ids)
            ).all()

            for record in persisted:
                self._publish_persisted_event(record)

            self._producer.flush(timeout=5)
            logger.info(
                f"[{incoming_event.transaction_id}] Recalculation completed and persisted {len(new_records)} positions."
            )

        # lock_release(lock_key)  # <-- Hook for future distributed lock

    def _publish_persisted_event(self, record: PositionHistory):
        if not record or not record.id:
            logger.error(f"[TXN:{getattr(record, 'transaction_id', 'Unknown')}] Cannot publish invalid record.")
            return

        try:
            event = PositionHistoryPersistedEvent.model_validate(record)
            self._producer.publish_message(
                topic=KAFKA_POSITION_HISTORY_PERSISTED_TOPIC,
                key=event.security_id,
                value=event.model_dump(mode="json", by_alias=True)
            )
            logger.debug(f"[TXN:{record.transaction_id}] Published PositionHistoryPersistedEvent ID={record.id}")

        except Exception as e:
            logger.error(
                f"[TXN:{record.transaction_id}] Publish failed for position_history_id={record.id}: {e}",
                exc_info=True
            )
