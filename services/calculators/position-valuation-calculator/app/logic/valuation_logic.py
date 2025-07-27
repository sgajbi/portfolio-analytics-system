import logging
from typing import Tuple
from decimal import Decimal

from portfolio_common.database_models import PositionHistory, MarketPrice

logger = logging.getLogger(__name__)

class ValuationLogic:
    """
    A stateless calculator for determining the market value and unrealized
    gain/loss of a position.
    """
    @staticmethod
    def calculate(position: PositionHistory, price: MarketPrice) -> Tuple[Decimal, Decimal]:
        """
        Calculates the market value and unrealized gain/loss.

        Args:
            position: The PositionHistory database object.
            price: The MarketPrice database object to value the position against.

        Returns:
            A tuple containing (market_value, unrealized_gain_loss).
        """
        if position.quantity == 0:
            return Decimal(0), Decimal(0)

        market_value = position.quantity * price.price
        unrealized_gain_loss = market_value - position.cost_basis
        
        logger.debug(
            f"Calculated valuation for position {position.id}: "
            f"MV={market_value}, UPL={unrealized_gain_loss}"
        )
        
        return market_value, unrealized_gain_loss