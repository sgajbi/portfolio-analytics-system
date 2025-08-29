# tests/unit/libs/performance-calculator-engine/test_calculator.py
import pytest
import pandas as pd
from decimal import Decimal
from datetime import date

from performance_calculator_engine.calculator import PerformanceCalculator
from performance_calculator_engine.constants import (
    DAILY_ROR_PCT,
    FINAL_CUMULATIVE_ROR_PCT,
    METRIC_BASIS_NET,
    METRIC_BASIS_GROSS,
    NIP,
    PERF_RESET,
    PERIOD_TYPE_YTD
)
from performance_calculator_engine.exceptions import InvalidInputDataError, MissingConfigurationError


@pytest.fixture
def sample_config() -> dict:
    """Provides a default configuration for the calculator."""
    return {
        "metric_basis": METRIC_BASIS_NET,
        "period_type": PERIOD_TYPE_YTD,
        "performance_start_date": "2024-12-31",
        "report_start_date": "2025-01-01",
        "report_end_date": "2025-01-05",
    }


@pytest.fixture
def sample_timeseries_data() -> list[dict]:
    """Provides a comprehensive list of daily time-series data for testing."""
    return [
        {
            "date": "2025-01-01",
            "bod_market_value": "0.0",
            "eod_market_value": "101000.0",
            "bod_cashflow": "100000.0",
            "eod_cashflow": "0.0",
            "fees": "-10.0"
        },
        {
            "date": "2025-01-02",
            "bod_market_value": "101000.0",
            "eod_market_value": "102500.0",
            "bod_cashflow": "0.0",
            "eod_cashflow": "0.0",
            "fees": "-12.0"
        },
        {
            "date": "2025-01-03",
            "bod_market_value": "102500.0",
            "eod_market_value": "108000.0",
            "bod_cashflow": "5000.0",
            "eod_cashflow": "0.0",
            "fees": "-10.0"
        },
        { # This is a No Investment Period (NIP)
            "date": "2025-01-04",
            "bod_market_value": "0.0",
            "eod_market_value": "0.0",
            "bod_cashflow": "1000.0",
            "eod_cashflow": "-1000.0",
            "fees": "0.0"
        },
        {
            "date": "2025-01-05",
            "bod_market_value": "108000.0",
            "eod_market_value": "107000.0",
            "bod_cashflow": "0.0",
            "eod_cashflow": "-2000.0",
            "fees": "-12.0"
        }
    ]


def test_full_calculation_logic(sample_config, sample_timeseries_data):
    """
    Tests the full iterative calculation logic, checking the final day's cumulative return.
    """
    # ARRANGE
    calculator = PerformanceCalculator(config=sample_config)

    # ACT
    results_df = calculator.calculate_performance(sample_timeseries_data)
    final_day_results = results_df.iloc[-1]

    # ASSERT
    # This assertion validates that the entire chain of calculations (linking, resets, etc.) is correct.
    # The expected value is derived from a manual trace of the logic with this specific input data.
    assert pytest.approx(final_day_results[FINAL_CUMULATIVE_ROR_PCT]) == 3.886716

    # Also check a key intermediate calculation on a prior day
    # FIX: Corrected expected value to be more precise.
    assert pytest.approx(results_df.iloc[2][FINAL_CUMULATIVE_ROR_PCT], abs=1e-6) == 2.944961
    
    # Verify the NIP flag was set correctly
    assert results_df.iloc[3][NIP] == 1
    assert results_df.iloc[2][NIP] == 0


def test_calculator_raises_on_missing_config():
    """
    Tests that the calculator raises a MissingConfigurationError if config is missing.
    """
    with pytest.raises(MissingConfigurationError):
        PerformanceCalculator(config=None)

    # FIX: Update the regex to match the actual error message.
    with pytest.raises(MissingConfigurationError, match="'performance_start_date' and 'report_end_date' are required"):
        PerformanceCalculator(config={"performance_start_date": "2025-01-01"})


def test_calculator_handles_empty_data_list(sample_config):
    """
    Tests that the calculator raises an InvalidInputDataError for an empty data list.
    """
    calculator = PerformanceCalculator(sample_config)
    with pytest.raises(InvalidInputDataError, match="cannot be empty"):
        calculator.calculate_performance([])