# tests/unit/services/calculators/position-valuation-calculator/logic/test_valuation_logic.py
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

def test_calculate_valuation_for_zero_quantity_position():
    """
    Tests that a zero-quantity position results in all zero valuation metrics.
    """
    result = ValuationLogic.calculate_valuation(
        quantity=Decimal("0"),
        market_price=Decimal("150"),
        cost_basis_base=Decimal("0"),
        cost_basis_local=Decimal("0"),
        price_currency="USD", instrument_currency="USD", portfolio_currency="USD"
    )
    assert result is not None
    mv_base, mv_local, pnl_base, pnl_local = result
    assert mv_base == Decimal("0")
    assert mv_local == Decimal("0")
    assert pnl_base == Decimal("0")
    assert pnl_local == Decimal("0")

def test_calculate_valuation_returns_none_if_fx_rate_missing():
    """
    Tests that the valuation fails (returns None) if a required FX rate is not provided.
    """
    # Scenario: Instrument(EUR) to Portfolio(USD) conversion is missing
    result = ValuationLogic.calculate_valuation(
        quantity=Decimal("100"),
        market_price=Decimal("120"),
        cost_basis_local=Decimal("10000"),
        cost_basis_base=Decimal("11000"),
        price_currency="EUR",
        instrument_currency="EUR",
        portfolio_currency="USD",
        instrument_to_portfolio_fx_rate=None # Missing rate
    )
    assert result is None

def test_calculate_valuation_with_price_currency_conversion():
    """
    Tests a full dual-FX conversion: Price(USD) -> Instrument(EUR) -> Portfolio(CHF).
    """
    result = ValuationLogic.calculate_valuation(
        quantity=Decimal("200"),
        market_price=Decimal("110"),           # Price is $110
        cost_basis_local=Decimal("20000"),     # Cost was €20,000
        cost_basis_base=Decimal("22000"),      # Cost was CHF 22,000
        price_currency="USD",
        instrument_currency="EUR",
        portfolio_currency="CHF",
        price_to_instrument_fx_rate=Decimal("0.90"), # 1 USD = 0.90 EUR
        instrument_to_portfolio_fx_rate=Decimal("0.95") # 1 EUR = 0.95 CHF
    )
    assert result is not None
    mv_base, mv_local, pnl_base, pnl_local = result

    # 1. Price in local (EUR): $110 * 0.90 EUR/USD = €99
    # 2. Market Value in local (EUR): 200 shares * €99 = €19,800
    assert mv_local == Decimal("19800")
    # 3. PnL in local (EUR): €19,800 - €20,000 = -€200
    assert pnl_local == Decimal("-200")

    # 4. Market Value in base (CHF): €19,800 * 0.95 CHF/EUR = CHF 18,810
    assert mv_base == Decimal("18810")
    # 5. PnL in base (CHF): CHF 18,810 - CHF 22,000 = -CHF 3,190
    assert pnl_base == Decimal("-3190")