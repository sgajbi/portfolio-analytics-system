import logging
from typing import Tuple, Optional
from decimal import Decimal

logger = logging.getLogger(__name__)

class ValuationLogic:
    """
    A stateless calculator for determining the market value and unrealized
    gain/loss of a position, now with FX conversion capabilities.
    """
    @staticmethod
    def calculate(
        quantity: Decimal,
        cost_basis: Decimal,
        market_price: Decimal,
        instrument_currency: str,
        portfolio_currency: str,
        fx_rate: Optional[Decimal] = None
    ) -> Tuple[Decimal, Decimal]:
        """
        Calculates market value and unrealized gain/loss, converting to the
        portfolio's base currency if necessary.
        """
        if quantity.is_zero():
            return Decimal(0), Decimal(0)

        # 1. Calculate market value in the instrument's local currency
        local_market_value = quantity * market_price
        
        # 2. Convert to portfolio's base currency if currencies differ
        if instrument_currency != portfolio_currency:
            if fx_rate is None:
                # This should be handled by the caller, but as a safeguard:
                logger.warning(
                    f"FX conversion required from {instrument_currency} to {portfolio_currency} but no rate was provided. "
                    "Valuation will be incorrect."
                )
                fx_rate = Decimal(1.0)
            
            # The cost basis is already in the portfolio currency.
            # We only need to convert the market value.
            final_market_value = local_market_value * fx_rate
        else:
            final_market_value = local_market_value

        # 3. Calculate unrealized gain/loss in the portfolio's currency
        unrealized_gain_loss = final_market_value - cost_basis
        
        logger.debug(
            f"Calculated valuation: MV={final_market_value} {portfolio_currency}, UPL={unrealized_gain_loss} {portfolio_currency}"
        )
        
        return final_market_value, unrealized_gain_loss