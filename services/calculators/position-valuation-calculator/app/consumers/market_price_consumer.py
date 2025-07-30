import logging
import json
from pydantic import ValidationError
from decimal import Decimal

from confluent_kafka import Message
from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.events import MarketPriceEvent, DailyPositionSnapshotPersistedEvent
from portfolio_common.db import get_db_session
from portfolio_common.database_models import PositionHistory, DailyPositionSnapshot
from portfolio_common.config import KAFKA_DAILY_POSITION_SNAPSHOT_PERSISTED_TOPIC

from ..repositories.valuation_repository import ValuationRepository
from ..logic.valuation_logic import ValuationLogic

logger = logging.getLogger(__name__)

class MarketPriceConsumer(BaseConsumer):
    """
    Consumes market price events and creates or updates a daily position snapshot
    with the new valuation.
    """

    async def process_message(self, msg: Message):
        key = msg.key().decode('utf-8') if msg.key() else "NoKey"
        value = msg.value().decode('utf-8')

        try:
            event_data = json.loads(value)
            price_event = MarketPriceEvent.model_validate(event_data)
            
            logger.info(f"Processing market price for {price_event.security_id} on {price_event.price_date}")
            
            with next(get_db_session()) as db:
                repo = ValuationRepository(db)
                
                portfolios_with_security = db.query(PositionHistory.portfolio_id).filter(
                    PositionHistory.security_id == price_event.security_id
                ).distinct().all()

                for portfolio_tuple in portfolios_with_security:
                    portfolio_id = portfolio_tuple[0]
                    self._create_or_update_snapshot(repo, portfolio_id, price_event)

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"Message validation failed for key '{key}': {e}. Value: '{value}'")
            await self._send_to_dlq(msg, e)
        except Exception as e:
            logger.error(f"Unexpected error processing message with key '{key}': {e}", exc_info=True)
            await self._send_to_dlq(msg, e)

    def _create_or_update_snapshot(self, repo: ValuationRepository, portfolio_id: str, price_event: MarketPriceEvent):
        """
        Creates or updates a daily position snapshot for a security within a portfolio.
        """
        latest_position = repo.get_latest_position_on_or_before(
            portfolio_id=portfolio_id,
            security_id=price_event.security_id,
            a_date=price_event.price_date
        )

        if not latest_position or latest_position.quantity == 0:
            return

        market_value, unrealized_gain_loss = ValuationLogic.calculate(
            quantity=latest_position.quantity,
            cost_basis=latest_position.cost_basis,
            market_price=price_event.price
        )

        snapshot = DailyPositionSnapshot(
            portfolio_id=portfolio_id,
            security_id=price_event.security_id,
            date=price_event.price_date,
            quantity=latest_position.quantity,
            cost_basis=latest_position.cost_basis,
            market_price=price_event.price,
            market_value=market_value,
            unrealized_gain_loss=unrealized_gain_loss
        )
        
        repo.upsert_daily_snapshot(snapshot)

        persisted_snapshot = repo.db.query(DailyPositionSnapshot).filter_by(
            portfolio_id=snapshot.portfolio_id,
            security_id=snapshot.security_id,
            date=snapshot.date
        ).first()

        if self._producer and persisted_snapshot:
            completion_event = DailyPositionSnapshotPersistedEvent.model_validate(persisted_snapshot)
            self._producer.publish_message(
                topic=KAFKA_DAILY_POSITION_SNAPSHOT_PERSISTED_TOPIC,
                key=completion_event.security_id,
                value=completion_event.model_dump(mode='json')
            )
            self._producer.flush(timeout=5)