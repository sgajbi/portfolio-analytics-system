import logging
import json
from pydantic import ValidationError

from confluent_kafka import Message
from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.events import PositionHistoryPersistedEvent
from portfolio_common.db import get_db_session
from portfolio_common.database_models import DailyPositionSnapshot # NEW IMPORT
from ..repositories.valuation_repository import ValuationRepository
from ..logic.valuation_logic import ValuationLogic

logger = logging.getLogger(__name__)

class PositionHistoryConsumer(BaseConsumer):
    """
    Consumes transaction-driven position history events, values them, and
    saves the result as a daily position snapshot.
    """

    async def process_message(self, msg: Message):
        key = msg.key().decode('utf-8') if msg.key() else "NoKey"
        value = msg.value().decode('utf-8')

        try:
            event_data = json.loads(value)
            position_event = PositionHistoryPersistedEvent.model_validate(event_data)
            
            logger.info(f"Valuing transaction-based position for id {position_event.position_history_id}")
            self._value_position(position_event)

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"Message validation failed for key '{key}': {e}. Value: '{value}'")
            await self._send_to_dlq(msg, e)
        except Exception as e:
            logger.error(f"Unexpected error processing message with key '{key}': {e}", exc_info=True)
            await self._send_to_dlq(msg, e)

    def _value_position(self, event: PositionHistoryPersistedEvent):
        """
        Fetches the full position and latest price, then calculates and saves
        a daily snapshot.
        """
        with next(get_db_session()) as db:
            try:
                repo = ValuationRepository(db)
                
                # Note: We still fetch the original PositionHistory record
                position = repo.get_position_by_id(event.position_history_id)
                if not position:
                    logger.warning(f"PositionHistory with id {event.position_history_id} not found. Cannot create snapshot.")
                    return

                price = repo.get_latest_price_for_position(
                    security_id=position.security_id,
                    position_date=position.position_date
                )
                
                market_price = price.price if price else None
                market_value, unrealized_gain_loss = None, None

                if market_price is not None:
                    market_value, unrealized_gain_loss = ValuationLogic.calculate(
                        quantity=position.quantity,
                        cost_basis=position.cost_basis,
                        market_price=market_price
                    )
                
                # Create the new snapshot record
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
                
                repo.upsert_daily_snapshot(snapshot)
                
            except Exception as e:
                logger.error(f"Failed during snapshot creation for position_history_id {event.position_history_id}: {e}", exc_info=True)