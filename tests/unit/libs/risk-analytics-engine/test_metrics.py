# tests/unit/libs/risk-analytics-engine/test_metrics.py
import pytest
import pandas as pd
import numpy as np
from datetime import date

from risk_analytics_engine.metrics import calculate_volatility, calculate_drawdown
from risk_analytics_engine.exceptions import InsufficientDataError

def test_calculate_volatility_happy_path():
    """
    GIVEN a simple series of returns with a known standard deviation
    WHEN calculate_volatility is called
    THEN it should return the correct annualized volatility.
    """
    # ARRANGE
    # A series of returns: -1%, 3%, -1%, 3%.
    # The sample standard deviation is approx. 2.3094.
    returns = pd.Series([-1.0, 3.0, -1.0, 3.0])
    annualization_factor = 252

    # ACT
    result = calculate_volatility(returns, annualization_factor)

    # ASSERT
    # The function calculates std_dev / 100 * sqrt(factor).
    # We assert against the same calculation to ensure correctness without hardcoding floating point numbers.
    expected_std_dev = returns.std()
    expected_volatility = (expected_std_dev / 100) * np.sqrt(annualization_factor)
    assert result == pytest.approx(expected_volatility)

def test_calculate_volatility_raises_for_insufficient_data():
    """
    GIVEN a return series with fewer than two data points
    WHEN calculate_volatility is called
    THEN it should raise an InsufficientDataError.
    """
    # ARRANGE
    returns_single = pd.Series([5.0])
    returns_empty = pd.Series([], dtype=float)

    # ACT & ASSERT
    with pytest.raises(InsufficientDataError):
        calculate_volatility(returns_single, 252)
    
    with pytest.raises(InsufficientDataError):
        calculate_volatility(returns_empty, 252)


def test_calculate_drawdown_happy_path():
    """
    GIVEN a return series with a clear peak and trough
    WHEN calculate_drawdown is called
    THEN it should return the correct max drawdown value and dates.
    """
    # ARRANGE
    dates = pd.to_datetime([
        "2025-01-01", "2025-01-02", "2025-01-03", "2025-01-04", "2025-01-05"
    ])
    # Wealth Index: 1000 -> 1050 -> 1029 -> 1059.87 -> 1017.4752 -> 1037.82...
    # Peak is 1059.87 on Jan 3. Trough is 1017.4752 on Jan 4.
    # Drawdown = (1017.4752 - 1059.87) / 1059.87 = -0.04
    returns = pd.Series([5.0, -2.0, 3.0, -4.0, 2.0], index=dates)

    # ACT
    result = calculate_drawdown(returns)

    # ASSERT
    assert result["max_drawdown"] == pytest.approx(-0.04)
    assert result["peak_date"] == date(2025, 1, 3)
    assert result["trough_date"] == date(2025, 1, 4)

def test_calculate_drawdown_raises_for_insufficient_data():
    """
    GIVEN an empty return series
    WHEN calculate_drawdown is called
    THEN it should raise an InsufficientDataError.
    """
    with pytest.raises(InsufficientDataError):
        calculate_drawdown(pd.Series([], dtype=float))