import logging
import json
from pydantic import ValidationError

from confluent_kafka import Message
from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.events import PositionHistoryPersistedEvent
from portfolio_common.db import get_db_session
from ..repositories.valuation_repository import ValuationRepository
from ..logic.valuation_logic import ValuationLogic

logger = logging.getLogger(__name__)

class PositionHistoryConsumer(BaseConsumer):
    """
    Consumes position history events and calculates the position's valuation
    based on the latest available market price.
    """

    async def process_message(self, msg: Message):
        key = msg.key().decode('utf-8') if msg.key() else "NoKey"
        value = msg.value().decode('utf-8')

        try:
            event_data = json.loads(value)
            position_event = PositionHistoryPersistedEvent.model_validate(event_data)
            
            logger.info(f"Processing position_history_id {position_event.position_history_id}")
            self._value_position(position_event)

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"Message validation failed for key '{key}': {e}. Value: '{value}'")
        except Exception as e:
            logger.error(f"Unexpected error processing message with key '{key}': {e}", exc_info=True)

    def _value_position(self, event: PositionHistoryPersistedEvent):
        """
        Fetches the full position and latest price, then calculates and saves the valuation.
        """
        with next(get_db_session()) as db:
            try:
                repo = ValuationRepository(db)
                
                position = repo.get_position_by_id(event.position_history_id)
                if not position:
                    logger.warning(f"Position with id {event.position_history_id} not found. Cannot value.")
                    return

                price = repo.get_latest_price_for_position(
                    security_id=position.security_id,
                    position_date=position.position_date
                )
                if not price:
                    logger.warning(f"No market price found for {position.security_id} on or before {position.position_date}. Cannot value.")
                    return

                market_value, unrealized_gain_loss = ValuationLogic.calculate(
                    quantity=position.quantity,
                    cost_basis=position.cost_basis,
                    market_price=price.price
                )
                
                repo.update_position_valuation(
                    position_history_id=position.id,
                    market_price=price.price,
                    market_value=market_value,
                    unrealized_gain_loss=unrealized_gain_loss
                )
                
            except Exception as e:
                logger.error(f"Failed during valuation for position_history_id {event.position_history_id}: {e}", exc_info=True)