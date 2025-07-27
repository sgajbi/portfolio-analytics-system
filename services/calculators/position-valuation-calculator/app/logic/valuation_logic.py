import logging
from typing import Tuple
from decimal import Decimal

logger = logging.getLogger(__name__)

class ValuationLogic:
    """
    A stateless calculator for determining the market value and unrealized
    gain/loss of a position.
    """
    @staticmethod
    def calculate(
        quantity: Decimal,
        cost_basis: Decimal,
        market_price: Decimal
    ) -> Tuple[Decimal, Decimal]:
        """
        Calculates the market value and unrealized gain/loss using primitive types.
        """
        if quantity == 0:
            return Decimal(0), Decimal(0)

        market_value = quantity * market_price
        unrealized_gain_loss = market_value - cost_basis
        
        logger.debug(
            f"Calculated valuation: MV={market_value}, UPL={unrealized_gain_loss}"
        )
        
        return market_value, unrealized_gain_loss