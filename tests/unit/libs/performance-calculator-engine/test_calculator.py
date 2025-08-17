# tests/unit/libs/performance-calculator-engine/test_calculator.py
import pytest
import pandas as pd
from decimal import Decimal

from performance_calculator_engine.calculator import PerformanceCalculator
from performance_calculator_engine.constants import (
    DAILY_ROR_PCT,
    METRIC_BASIS_NET,
    METRIC_BASIS_GROSS
)
from performance_calculator_engine.exceptions import InvalidInputDataError

@pytest.fixture
def sample_timeseries_data() -> list[dict]:
    """Provides a sample list of daily time-series data for testing."""
    return [
        { # Day 1: Initial investment, 1% gross gain
            "date": "2025-01-01",
            "bod_market_value": "0.0",
            "eod_market_value": "101000.0",
            "bod_cashflow": "100000.0",
            "eod_cashflow": "0.0",
            "fees": "-10.0"
        },
        { # Day 2: No cashflow, further gain
            "date": "2025-01-02",
            "bod_market_value": "101000.0",
            "eod_market_value": "102500.0",
            "bod_cashflow": "0.0",
            "eod_cashflow": "0.0",
            "fees": "-12.0"
        },
        { # Day 3: Deposit, small loss
            "date": "2025-01-03",
            "bod_market_value": "102500.0",
            "eod_market_value": "107000.0",
            "bod_cashflow": "5000.0",
            "eod_cashflow": "0.0",
            "fees": "-15.0"
        },
        { # Day 4: Zero denominator case
            "date": "2025-01-04",
            "bod_market_value": "0.0",
            "eod_market_value": "0.0",
            "bod_cashflow": "0.0",
            "eod_cashflow": "0.0",
            "fees": "0.0"
        }
    ]

def test_calculate_daily_ror_net_basis(sample_timeseries_data):
    """
    Tests that daily RoR is calculated correctly on a NET basis (including fees).
    """
    # ARRANGE
    calculator = PerformanceCalculator(metric_basis=METRIC_BASIS_NET)

    # ACT
    results_df = calculator.calculate_performance(sample_timeseries_data)
    results = results_df[DAILY_ROR_PCT].apply(lambda x: round(x, 6)).tolist()

    # ASSERT
    # Day 1: (101000 - 0 - 100000 + (-10)) / (0 + 100000) = 990 / 100000 = 0.99%
    assert results[0] == Decimal("0.990000")
    # Day 2: (102500 - 101000 - 0 + (-12)) / (101000 + 0) = 1488 / 101000 = 1.473267%
    assert results[1] == Decimal("1.473267")
    # Day 3: (107000 - 102500 - 5000 + (-15)) / (102500 + 5000) = -515 / 107500 = -0.479070%
    assert results[2] == Decimal("-0.479070")
    # Day 4: Zero denominator should result in 0% RoR
    assert results[3] == Decimal("0.000000")

def test_calculate_daily_ror_gross_basis(sample_timeseries_data):
    """
    Tests that daily RoR is calculated correctly on a GROSS basis (excluding fees).
    """
    # ARRANGE
    calculator = PerformanceCalculator(metric_basis=METRIC_BASIS_GROSS)

    # ACT
    results_df = calculator.calculate_performance(sample_timeseries_data)
    results = results_df[DAILY_ROR_PCT].apply(lambda x: round(x, 6)).tolist()

    # ASSERT
    # Day 1: (101000 - 0 - 100000) / (0 + 100000) = 1000 / 100000 = 1.0%
    assert results[0] == Decimal("1.000000")
    # Day 2: (102500 - 101000 - 0) / (101000 + 0) = 1500 / 101000 = 1.485149%
    assert results[1] == Decimal("1.485149")
    # Day 3: (107000 - 102500 - 5000) / (102500 + 5000) = -500 / 107500 = -0.465116%
    assert results[2] == Decimal("-0.465116")
    # Day 4: Zero denominator should result in 0% RoR
    assert results[3] == Decimal("0.000000")

def test_calculator_raises_on_invalid_basis():
    """
    Tests that the calculator raises an InvalidInputDataError for an invalid metric basis.
    """
    with pytest.raises(InvalidInputDataError, match="Invalid 'metric_basis'"):
        PerformanceCalculator(metric_basis="INVALID_BASIS")

def test_calculator_raises_on_empty_data():
    """
    Tests that the calculator raises an InvalidInputDataError if the input list is empty.
    """
    calculator = PerformanceCalculator()
    with pytest.raises(InvalidInputDataError, match="cannot be empty"):
        calculator.calculate_performance([])