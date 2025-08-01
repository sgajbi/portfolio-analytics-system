# services/calculators/position-valuation-calculator/app/consumers/market_price_consumer.py
import logging
import json
from pydantic import ValidationError

from confluent_kafka import Message
from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.events import MarketPriceEvent, DailyPositionSnapshotPersistedEvent
from portfolio_common.db import get_db_session
from portfolio_common.database_models import PositionHistory, DailyPositionSnapshot
from portfolio_common.config import KAFKA_DAILY_POSITION_SNAPSHOT_PERSISTED_TOPIC
from portfolio_common.idempotency_repository import IdempotencyRepository

from ..repositories.valuation_repository import ValuationRepository
from ..logic.valuation_logic import ValuationLogic

logger = logging.getLogger(__name__)

SERVICE_NAME = "position-valuation-calculator-from-price" # NEW: Unique service name

class MarketPriceConsumer(BaseConsumer):
    """
    Consumes market price events and creates or updates daily position snapshots
    for all affected portfolios with the new valuation. This process is idempotent.
    """

    async def process_message(self, msg: Message):
        key = msg.key().decode('utf-8') if msg.key() else "NoKey"
        value = msg.value().decode('utf-8')
        event_id = f"{msg.topic()}-{msg.partition()}-{msg.offset()}"
        updated_snapshots = []

        try:
            event_data = json.loads(value)
            price_event = MarketPriceEvent.model_validate(event_data)
            
            logger.info(f"Processing market price for {price_event.security_id} on {price_event.price_date}", extra={"event_id": event_id})
            
            with next(get_db_session()) as db:
                with db.begin(): # Atomically check, process, and mark
                    idempotency_repo = IdempotencyRepository(db)
                    if idempotency_repo.is_event_processed(event_id, SERVICE_NAME):
                        logger.warning(f"Event {event_id} already processed. Skipping.")
                        return

                    repo = ValuationRepository(db)
                    
                    # Find all distinct portfolio IDs that hold this security
                    portfolios_with_security = db.query(PositionHistory.portfolio_id).filter(
                        PositionHistory.security_id == price_event.security_id
                    ).distinct().all()

                    for portfolio_tuple in portfolios_with_security:
                        portfolio_id = portfolio_tuple[0]
                        snapshot = self._create_or_update_snapshot(repo, portfolio_id, price_event)
                        if snapshot:
                            updated_snapshots.append(snapshot)
                    
                    # Mark the single incoming price event as processed
                    idempotency_repo.mark_event_processed(event_id, "N/A", SERVICE_NAME)

            # Publish events for all updated snapshots after the transaction commits
            if self._producer and updated_snapshots:
                for snapshot in updated_snapshots:
                    completion_event = DailyPositionSnapshotPersistedEvent.model_validate(snapshot)
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

    def _create_or_update_snapshot(
        self, repo: ValuationRepository, portfolio_id: str, price_event: MarketPriceEvent
    ) -> DailyPositionSnapshot | None:
        """
        Calculates and upserts a daily position snapshot for one security within one portfolio.
        Returns the upserted snapshot object.
        """
        latest_position = repo.get_latest_position_on_or_before(
            portfolio_id=portfolio_id,
            security_id=price_event.security_id,
            a_date=price_event.price_date
        )

        if not latest_position or latest_position.quantity.is_zero():
            return None

        market_value, unrealized_gain_loss = ValuationLogic.calculate(
            quantity=latest_position.quantity,
            cost_basis=latest_position.cost_basis,
            market_price=price_event.price
        )

        snapshot_to_save = DailyPositionSnapshot(
            portfolio_id=portfolio_id,
            security_id=price_event.security_id,
            date=price_event.price_date,
            quantity=latest_position.quantity,
            cost_basis=latest_position.cost_basis,
            market_price=price_event.price,
            market_value=market_value,
            unrealized_gain_loss=unrealized_gain_loss
        )
        
        # Use the repository method that now returns the persisted object
        return repo.upsert_daily_snapshot(snapshot_to_save)