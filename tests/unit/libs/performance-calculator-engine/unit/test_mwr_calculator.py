# tests/unit/libs/performance-calculator-engine/unit/test_mwr_calculator.py
import pytest
from decimal import Decimal
from datetime import date

from performance_calculator_engine.mwr_calculator import MWRCalculator

@pytest.fixture
def calculator() -> MWRCalculator:
    """Provides a clean instance of the MWRCalculator."""
    return MWRCalculator()

def test_mwr_calculator_can_be_instantiated(calculator: MWRCalculator):
    """
    Tests that the MWRCalculator class can be instantiated without errors.
    """
    assert calculator is not None

def test_compute_xirr_simple_case(calculator: MWRCalculator):
    """
    Tests a simple case with one initial investment and one final value.
    -100 invested on day 0, returns 110 on day 365. IRR should be 10%.
    """
    cashflows = [
        (date(2024, 1, 1), Decimal("-100")),
        (date(2025, 1, 1), Decimal("110")),
    ]
    result = calculator.compute_xirr(cashflows)
    assert result is not None
    assert pytest.approx(result) == Decimal("0.1")

def test_compute_xirr_multiple_flows(calculator: MWRCalculator):
    """
    Tests a more complex case with multiple cashflows.
    Verified with Excel's XIRR function.
    """
    cashflows = [
        (date(2024, 1, 1), Decimal("-1000")),
        (date(2024, 4, 1), Decimal("-500")),
        (date(2024, 8, 15), Decimal("300")),
        (date(2025, 1, 1), Decimal("1300")),
    ]
    result = calculator.compute_xirr(cashflows)
    assert result is not None
    # Excel XIRR result for this data is 5.432%
    assert pytest.approx(result, abs=1e-5) == Decimal("0.05432")

def test_compute_xirr_no_sign_change_returns_none(calculator: MWRCalculator):
    """
    Tests that XIRR returns None if all cashflows are positive or all are negative.
    """
    all_positive = [
        (date(2024, 1, 1), Decimal("100")),
        (date(2024, 6, 1), Decimal("200")),
    ]
    all_negative = [
        (date(2024, 1, 1), Decimal("-100")),
        (date(2024, 6, 1), Decimal("-200")),
    ]
    assert calculator.compute_xirr(all_positive) is None
    assert calculator.compute_xirr(all_negative) is None

def test_compute_xirr_insufficient_data_returns_none(calculator: MWRCalculator):
    """
    Tests that XIRR returns None if there are fewer than two cashflows.
    """
    assert calculator.compute_xirr([]) is None
    assert calculator.compute_xirr([(date(2024, 1, 1), Decimal("-100"))]) is None