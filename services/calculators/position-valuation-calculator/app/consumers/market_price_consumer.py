import logging
import json
from pydantic import ValidationError
from decimal import Decimal

from confluent_kafka import Message
from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.events import MarketPriceEvent, PositionHistoryPersistedEvent
from portfolio_common.db import get_db_session
from portfolio_common.database_models import PositionHistory
from portfolio_common.config import KAFKA_POSITION_HISTORY_PERSISTED_TOPIC
from ..repositories.valuation_repository import ValuationRepository
from ..logic.valuation_logic import ValuationLogic

logger = logging.getLogger(__name__)

class MarketPriceConsumer(BaseConsumer):
    """
    Consumes market price events. It re-calculates valuations for any existing
    positions on the same date or creates a new daily position snapshot if the
    latest position is from a previous day.
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
                
                # Find all portfolios that hold this security
                portfolios_with_security = db.query(PositionHistory.portfolio_id).filter(
                    PositionHistory.security_id == price_event.security_id
                ).distinct().all()

                for portfolio_tuple in portfolios_with_security:
                    portfolio_id = portfolio_tuple[0]
                    self._value_position_for_portfolio(repo, portfolio_id, price_event)

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"Message validation failed for key '{key}': {e}. Value: '{value}'")
            await self._send_to_dlq(msg, e)
        except Exception as e:
            logger.error(f"Unexpected error processing message with key '{key}': {e}", exc_info=True)
            await self._send_to_dlq(msg, e)

    def _value_position_for_portfolio(self, repo: ValuationRepository, portfolio_id: str, price_event: MarketPriceEvent):
        """
        Calculates valuation for a security within a single portfolio, creating a
        new snapshot if necessary.
        """
        latest_position = repo.get_latest_position_on_or_before(
            portfolio_id=portfolio_id,
            security_id=price_event.security_id,
            a_date=price_event.price_date
        )

        if not latest_position or latest_position.quantity == 0:
            return # No active position to value

        market_value, unrealized_gain_loss = ValuationLogic.calculate(
            quantity=latest_position.quantity,
            cost_basis=latest_position.cost_basis,
            market_price=price_event.price
        )

        if latest_position.position_date == price_event.price_date:
            # The position is from today, just update it
            updated_position = repo.update_position_valuation(
                position_history_id=latest_position.id,
                market_price=price_event.price,
                market_value=market_value,
                unrealized_gain_loss=unrealized_gain_loss
            )
        else:
            # The latest position is from a previous day, create a new snapshot for today
            new_snapshot = PositionHistory(
                portfolio_id=latest_position.portfolio_id,
                security_id=latest_position.security_id,
                transaction_id=latest_position.transaction_id, # Carry over the last transaction ID
                position_date=price_event.price_date,
                quantity=latest_position.quantity, # Carry over
                cost_basis=latest_position.cost_basis, # Carry over
                market_price=price_event.price,
                market_value=market_value,
                unrealized_gain_loss=unrealized_gain_loss
            )
            updated_position = repo.create_position_snapshot(new_snapshot)

        # Publish an event for the new/updated snapshot to trigger downstream services
        if updated_position and self._producer:
            completion_event = PositionHistoryPersistedEvent.model_validate(updated_position)
            self._producer.publish_message(
                topic=KAFKA_POSITION_HISTORY_PERSISTED_TOPIC,
                key=completion_event.security_id,
                value=completion_event.model_dump(mode='json', by_alias=True)
            )
            self._producer.flush(timeout=5)