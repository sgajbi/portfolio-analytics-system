# tests/unit/libs/risk-analytics-engine/test_metrics.py
import pytest
import pandas as pd
import numpy as np

from risk_analytics_engine.metrics import calculate_volatility
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