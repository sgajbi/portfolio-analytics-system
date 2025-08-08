# services/calculators/position-valuation-calculator/app/logic/valuation_logic.py
import logging
from typing import Tuple, Optional
from decimal import Decimal

logger = logging.getLogger(__name__)

class ValuationLogic:
    """
    A stateless calculator for determining the market value of a position
    in the instrument's local currency.
    """
    @staticmethod
    def calculate_market_value(
        quantity: Decimal,
        market_price: Decimal,
        price_currency: str,
        instrument_currency: str,
        fx_rate: Optional[Decimal] = None
    ) -> Optional[Decimal]:
        """
        Calculates the market value in the instrument's currency, converting the
        price if necessary. Returns None if conversion is needed but no rate is provided.
        """
        if quantity.is_zero():
            return Decimal(0)

        # 1. Determine the price in the instrument's currency
        valuation_price = market_price
        if price_currency != instrument_currency:
            if fx_rate is None:
                logger.warning(
                    f"FX conversion for price required from {price_currency} to {instrument_currency} but no rate was provided. "
                    "Cannot calculate market value."
                )
                return None # Cannot proceed without a valid price
            valuation_price = market_price * fx_rate

        # 2. Calculate market value in the instrument's local currency
        market_value = quantity * valuation_price
        
        logger.debug(
            f"Calculated market value: {market_value} {instrument_currency}"
        )
        return market_value