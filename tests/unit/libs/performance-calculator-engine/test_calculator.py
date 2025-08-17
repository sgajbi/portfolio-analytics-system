# tests/unit/libs/performance-calculator-engine/test_calculator.py
import pytest
from decimal import Decimal

from performance_calculator_engine.calculator import PerformanceEngine
from performance_calculator_engine.constants import METRIC_BASIS_NET, METRIC_BASIS_GROSS
from performance_calculator_engine.exceptions import CalculationLogicError

def test_calculate_daily_metrics_first_day():
    """
    Tests calculation for the first day of a portfolio's history.
    BOD Market Value should be 0.
    """
    # ARRANGE
    current_day_ts = {
        'eod_market_value': Decimal("10050"),
        'bod_cashflow': Decimal("10000"),
        'eod_cashflow': Decimal("0"),
        'fees': Decimal("5")
    }

    # ACT
    result = PerformanceEngine.calculate_daily_metrics(current_day_ts, None)

    # ASSERT
    # Gross Profit = 10050 - 0 - 10000 = 50
    # Denominator = 0 + 10000 = 10000
    # Gross Return = (50 / 10000) * 100 = 0.5%
    assert pytest.approx(result[METRIC_BASIS_GROSS]) == Decimal("0.5")

    # Net Profit = 50 - 5 = 45
    # Net Return = (45 / 10000) * 100 = 0.45%
    assert pytest.approx(result[METRIC_BASIS_NET]) == Decimal("0.45")

def test_calculate_daily_metrics_subsequent_day():
    """
    Tests calculation for a subsequent day with various cashflows and fees.
    """
    # ARRANGE
    previous_day_ts = {'eod_market_value': Decimal("10050")}
    current_day_ts = {
        'eod_market_value': Decimal("10200"),
        'bod_cashflow': Decimal("100"),
        'eod_cashflow': Decimal("-50"),
        'fees': Decimal("2")
    }

    # ACT
    result = PerformanceEngine.calculate_daily_metrics(current_day_ts, previous_day_ts)

    # ASSERT
    # Net Cashflow = 100 - 50 = 50
    # Change in MV = 10200 - 10050 = 150
    # Denominator = 10050 + 50 = 10100
    # Gross Profit = 150 - 50 = 100
    # Gross Return = (100 / 10100) * 100 = 0.990099...%
    assert pytest.approx(result[METRIC_BASIS_GROSS]) == Decimal("0.990099")

    # Net Profit = 100 - 2 = 98
    # Net Return = (98 / 10100) * 100 = 0.970297...%
    assert pytest.approx(result[METRIC_BASIS_NET]) == Decimal("0.970297")

def test_calculate_daily_metrics_raises_on_missing_data():
    """
    Tests that a CalculationLogicError is raised if the input data is malformed.
    """
    # ARRANGE
    # 'eod_market_value' is missing
    malformed_ts = {'bod_cashflow': Decimal(0), 'fees': Decimal(0)}

    # ACT & ASSERT
    with pytest.raises(CalculationLogicError):
        PerformanceEngine.calculate_daily_metrics(malformed_ts, None)