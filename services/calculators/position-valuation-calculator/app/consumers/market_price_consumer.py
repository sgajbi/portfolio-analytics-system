import logging
import json
from pydantic import ValidationError
from decimal import Decimal

from confluent_kafka import Message
from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.events import MarketPriceEvent
from portfolio_common.db import get_db_session
from ..repositories.valuation_repository import ValuationRepository
from ..logic.valuation_logic import ValuationLogic

logger = logging.getLogger(__name__)

class MarketPriceConsumer(BaseConsumer):
    """
    Consumes market price events and re-calculates valuations for any
    positions on the same date.
    """

    async def process_message(self, msg: Message):
        key = msg.key().decode('utf-8') if msg.key() else "NoKey"
        value = msg.value().decode('utf-8')

        try:
            event_data = json.loads(value)
            price_event = MarketPriceEvent.model_validate(event_data)
            
            logger.info(f"Processing market price for {price_event.security_id} on {price_event.price_date}")
            self._value_positions_for_price(price_event)

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"Message validation failed for key '{key}': {e}. Value: '{value}'")
            # In a real scenario, you might send this to a DLQ
        except Exception as e:
            logger.error(f"Unexpected error processing message with key '{key}': {e}", exc_info=True)

    def _value_positions_for_price(self, price_event: MarketPriceEvent):
        """
        Finds and re-values all positions matching the security and date of the price event.
        """
        with next(get_db_session()) as db:
            try:
                repo = ValuationRepository(db)
                
                # Find all positions for this security on the exact same date
                positions_to_value = repo.get_positions_for_price(
                    security_id=price_event.security_id,
                    price_date=price_event.price_date
                )

                if not positions_to_value:
                    logger.info(f"No positions found for {price_event.security_id} on {price_event.price_date}. Nothing to value.")
                    return
                
                logger.info(f"Found {len(positions_to_value)} position(s) to re-value for {price_event.security_id} on {price_event.price_date}.")

                # The price object is a Pydantic model, but our logic expects a DB model.
                # For this limited case, we can construct a mock DB object or just pass the price decimal.
                # Let's pass the price value directly for simplicity.
                # NOTE: A more robust implementation might fetch the price DB object.
                mock_price_object_for_logic = type('MarketPrice', (object,), {'price': price_event.price})


                for position in positions_to_value:
                    market_value, unrealized_gain_loss = ValuationLogic.calculate(position, mock_price_object_for_logic)
                    
                    repo.update_position_valuation(
                        position_history_id=position.id,
                        market_price=price_event.price,
                        market_value=market_value,
                        unrealized_gain_loss=unrealized_gain_loss
                    )
                
                logger.info(f"Successfully re-valued {len(positions_to_value)} position(s).")

            except Exception as e:
                logger.error(f"Failed during valuation for price event {price_event.security_id}: {e}", exc_info=True)
                # The session will be rolled back by the `with` block's error handling.