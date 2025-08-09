# services/calculators/position-valuation-calculator/tests/unit/logic/test_valuation_logic.py
import pytest
from decimal import Decimal
from typing import Optional, Tuple

# Corrected absolute import
from services.calculators.position_valuation_calculator.app.logic.valuation_logic import ValuationLogic

def test_calculate_valuation_with_gain_same_currency():
    """
    Tests a standard valuation scenario resulting in an unrealized gain
    where all currencies (price, instrument, portfolio) are the same.
    """
    result = ValuationLogic.calculate_valuation(
        quantity=Decimal("100"),
        market_price=Decimal("120"),
        cost_basis_base=Decimal("10000"),
        cost_basis_local=Decimal("10000"),
        price_currency="USD",
        instrument_currency="USD",
        portfolio_currency="USD"
    )
    assert result is not None
    mv_base, mv_local, pnl_base, pnl_local = result

    # Expected MV = 100 * 120 = 12000
    assert mv_local == Decimal("12000")
    assert mv_base == Decimal("12000")
    # Expected UGL = 12000 - 10000 = 2000
    assert pnl_local == Decimal("2000")
    assert pnl_base == Decimal("2000")

def test_calculate_valuation_with_fx_conversion():
    """
    Tests a valuation scenario where the instrument/price is in EUR
    and the portfolio is in USD, requiring FX conversion.
    """
    result = ValuationLogic.calculate_valuation(
        quantity=Decimal("100"),                 # 100 shares
        market_price=Decimal("120"),              # €120 per share
        cost_basis_local=Decimal("10000"),        # Total cost was €10,000
        cost_basis_base=Decimal("11000"),         # Total cost was $11,000 (at a 1.1 FX rate)
        price_currency="EUR",
        instrument_currency="EUR",
        portfolio_currency="USD",
        price_to_instrument_fx_rate=None,         # Price is already in instrument currency
        instrument_to_portfolio_fx_rate=Decimal("1.2") # Current FX rate is 1.2
    )
    assert result is not None
    mv_base, mv_local, pnl_base, pnl_local = result

    # Local (EUR) calculations
    assert mv_local == Decimal("12000")   # 100 shares * €120
    assert pnl_local == Decimal("2000")   # €12,000 MV - €10,000 cost

    # Base (USD) calculations
    assert mv_base == Decimal("14400")    # €12,000 MV * 1.2 FX rate
    assert pnl_base == Decimal("3400")    # $14,400 MV - $11,000 cost