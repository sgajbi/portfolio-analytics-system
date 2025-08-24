# tests/unit/libs/performance-calculator-engine/unit/test_mwr_calculator.py
import pytest
from decimal import Decimal
from datetime import date
from unittest.mock import patch

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

# --- Tests for compute_xirr ---

def test_compute_xirr_simple_case(calculator: MWRCalculator):
    """
    Tests a simple case with one initial investment and one final value.
    -100 invested on day 0, returns 110 on day 366 (2024 is a leap year).
    IRR should be ~9.97%.
    """
    cashflows = [
        (date(2024, 1, 1), Decimal("-100")),
        (date(2025, 1, 1), Decimal("110")),
    ]
    result = calculator.compute_xirr(cashflows)
    assert result is not None
    # The expected value is 1.1^(365/366) - 1
    assert result == pytest.approx(Decimal("0.0997135859"))

def test_compute_xirr_multiple_flows(calculator: MWRCalculator):
    """
    Tests a more complex case with multiple cashflows.
    """
    cashflows = [
        (date(2024, 1, 1), Decimal("-1000")),
        (date(2024, 4, 1), Decimal("-500")),
        (date(2024, 8, 15), Decimal("300")),
        (date(2025, 1, 1), Decimal("1300")),
    ]
    result = calculator.compute_xirr(cashflows)
    assert result is not None
    # Correct calculated value for this data set.
    assert result == pytest.approx(Decimal("0.0790865455"))

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

# --- Tests for compute_period_mwr ---

def test_compute_period_mwr_assembles_timeline_correctly(calculator: MWRCalculator):
    """
    Tests that compute_period_mwr correctly assembles the investor-sign cashflow
    timeline and calls the XIRR solver.
    """
    # ARRANGE
    start_date, end_date = date(2024, 1, 1), date(2025, 1, 1)
    begin_mv, end_mv = Decimal("1000"), Decimal("1300")
    # Portfolio sign: deposit is positive
    external_flows = [(date(2024, 6, 1), Decimal("100"))] 
    
    # Expected timeline for solver (investor sign)
    expected_timeline = [
        (start_date, Decimal("-1000")), # Investor outflow
        (date(2024, 6, 1), Decimal("-100")),     # Investor outflow
        (end_date, Decimal("1300")),   # Investor inflow
    ]

    # Mock the underlying solver to just check the input it receives
    with patch.object(calculator, 'compute_xirr', return_value=Decimal("0.123")) as mock_xirr:
        # ACT
        result = calculator.compute_period_mwr(
            start_date, end_date, begin_mv, end_mv, external_flows
        )

        # ASSERT
        mock_xirr.assert_called_once()
        # The list might be in a different order, so we compare sorted lists of tuples
        actual_timeline = mock_xirr.call_args[0][0]
        assert sorted(actual_timeline) == sorted(expected_timeline)
        assert result["mwr"] == Decimal("0.123")

def test_compute_period_mwr_annualization_logic(calculator: MWRCalculator):
    """
    Tests that annualization is correctly handled based on the period length.
    """
    # ARRANGE
    # A period greater than one year
    long_start, long_end = date(2023, 1, 1), date(2025, 1, 1)
    # A period less than one year
    short_start, short_end = date(2024, 1, 1), date(2024, 6, 1)

    # Mock the solver to return a fixed value
    with patch.object(calculator, 'compute_xirr', return_value=Decimal("0.15")):
        # ACT
        long_period_result = calculator.compute_period_mwr(
            long_start, long_end, Decimal(1), Decimal(1), []
        )
        short_period_result = calculator.compute_period_mwr(
            short_start, short_end, Decimal(1), Decimal(1), []
        )
        short_period_no_annualize = calculator.compute_period_mwr(
            short_start, short_end, Decimal(1), Decimal(1), [], annualize=False
        )
        
    # ASSERT
    assert long_period_result["mwr"] == Decimal("0.15")
    assert long_period_result["mwr_annualized"] == Decimal("0.15")

    assert short_period_result["mwr"] == Decimal("0.15")
    assert short_period_result["mwr_annualized"] is None

    assert short_period_no_annualize["mwr"] == Decimal("0.15")
    assert short_period_no_annualize["mwr_annualized"] is None