# services/calculators/position-valuation-calculator/tests/unit/logic/test_valuation_logic.py
import pytest
from decimal import Decimal

from logic.valuation_logic import ValuationLogic

def test_calculate_valuation_with_gain():
    """
    Tests a standard valuation scenario resulting in an unrealized gain.
    """
    quantity = Decimal("100")
    cost_basis = Decimal("10000")  # Avg cost: $100/share
    market_price = Decimal("120")   # Market price: $120/share

    market_value, unrealized_gain_loss = ValuationLogic.calculate(
        quantity=quantity,
        cost_basis=cost_basis,
        market_price=market_price
    )

    # Expected MV = 100 * 120 = 12000
    # Expected UGL = 12000 - 10000 = 2000
    assert market_value == Decimal("12000")
    assert unrealized_gain_loss == Decimal("2000")

def test_calculate_valuation_with_loss():
    """
    Tests a valuation scenario resulting in an unrealized loss.
    """
    quantity = Decimal("50")
    cost_basis = Decimal("5000")   # Avg cost: $100/share
    market_price = Decimal("85")    # Market price: $85/share

    market_value, unrealized_gain_loss = ValuationLogic.calculate(
        quantity=quantity,
        cost_basis=cost_basis,
        market_price=market_price
    )

    # Expected MV = 50 * 85 = 4250
    # Expected UGL = 4250 - 5000 = -750
    assert market_value == Decimal("4250")
    assert unrealized_gain_loss == Decimal("-750")

def test_calculate_valuation_with_zero_quantity():
    """
    Tests that a position with zero quantity has zero market value and gain/loss.
    """
    quantity = Decimal("0")
    cost_basis = Decimal("0")
    market_price = Decimal("150")

    market_value, unrealized_gain_loss = ValuationLogic.calculate(
        quantity=quantity,
        cost_basis=cost_basis,
        market_price=market_price
    )

    assert market_value == Decimal("0")
    assert unrealized_gain_loss == Decimal("0")