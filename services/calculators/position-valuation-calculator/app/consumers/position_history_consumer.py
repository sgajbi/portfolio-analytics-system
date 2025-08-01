# services/calculators/position-valuation-calculator/app/consumers/position_history_consumer.py
import logging
import json
from pydantic import ValidationError

from confluent_kafka import Message
from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.events import PositionHistoryPersistedEvent, DailyPositionSnapshotPersistedEvent
from portfolio_common.db import get_db_session
from portfolio_common.database_models import DailyPositionSnapshot, PositionHistory
from portfolio_common.config import KAFKA_DAILY_POSITION_SNAPSHOT_PERSISTED_TOPIC
from portfolio_common.idempotency_repository import IdempotencyRepository # NEW IMPORT
from ..repositories.valuation_repository import ValuationRepository
from ..logic.valuation_logic import ValuationLogic

logger = logging.getLogger(__name__)

SERVICE_NAME = "position-valuation-calculator-from-position" # NEW: Unique service name

class PositionHistoryConsumer(BaseConsumer):
    """
    Consumes transaction-driven position history events, values them, and
    saves the result as a daily position snapshot. This process is idempotent.
    """

    async def process_message(self, msg: Message):
        key = msg.key().decode('utf-8') if msg.key() else "NoKey"
        value = msg.value().decode('utf-8')
        event_id = f"{msg.topic()}-{msg.partition()}-{msg.offset()}"
        persisted_snapshot = None

        try:
            event_data = json.loads(value)
            position_event = PositionHistoryPersistedEvent.model_validate(event_data)
            
            logger.info(f"Valuing transaction-based position for id {position_event.id}", extra={"event_id": event_id})
            
            with next(get_db_session()) as db:
                with db.begin(): # Atomically check, process, and mark
                    idempotency_repo = IdempotencyRepository(db)
                    if idempotency_repo.is_event_processed(event_id, SERVICE_NAME):
                        logger.warning(f"Event {event_id} already processed. Skipping.")
                        return

                    repo = ValuationRepository(db)
                    
                    position = db.query(PositionHistory).get(position_event.id)
                    if not position:
                        logger.warning(f"PositionHistory with id {position_event.id} not found. Marking as processed to skip.")
                        idempotency_repo.mark_event_processed(event_id, position_event.portfolio_id, SERVICE_NAME)
                        return

                    price = repo.get_latest_price_for_position(
                        security_id=position.security_id,
                        position_date=position.position_date
                    )
                    
                    market_price = None
                    market_value, unrealized_gain_loss = None, None

                    if price:
                        market_price = price.price
                        market_value, unrealized_gain_loss = ValuationLogic.calculate(
                            quantity=position.quantity,
                            cost_basis=position.cost_basis,
                            market_price=market_price
                        )
                    else:
                        logger.warning(f"No market price for {position.security_id} on or before {position.position_date}. Creating un-valued snapshot.")
                    
                    snapshot = DailyPositionSnapshot(
                        portfolio_id=position.portfolio_id,
                        security_id=position.security_id,
                        date=position.position_date,
                        quantity=position.quantity,
                        cost_basis=position.cost_basis,
                        market_price=market_price,
                        market_value=market_value,
                        unrealized_gain_loss=unrealized_gain_loss
                    )
                    
                    repo.upsert_daily_snapshot(snapshot) # This method no longer commits
                    idempotency_repo.mark_event_processed(event_id, position.portfolio_id, SERVICE_NAME)

                # Fetch the upserted record back to get its ID for publishing
                persisted_snapshot = db.query(DailyPositionSnapshot).filter_by(
                    portfolio_id=snapshot.portfolio_id,
                    security_id=snapshot.security_id,
                    date=snapshot.date
                ).first()

            # Publish event after the transaction commits
            if self._producer and persisted_snapshot:
                completion_event = DailyPositionSnapshotPersistedEvent.model_validate(persisted_snapshot)
                self._producer.publish_message(
                    topic=KAFKA_DAILY_POSITION_SNAPSHOT_PERSISTED_TOPIC,
                    key=completion_event.security_id,
                    value=completion_event.model_dump(mode='json')
                )
                self._producer.flush(timeout=5)

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"Message validation failed for key '{key}': {e}. Value: '{value}'", exc_info=True)
            await self._send_to_dlq(msg, e)
        except Exception as e:
            logger.error(f"Unexpected error processing message with key '{key}': {e}", exc_info=True)
            await self._send_to_dlq(msg, e)