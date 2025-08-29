# tests/unit/libs/risk-analytics-engine/test_metrics.py
import pytest
import pandas as pd
import numpy as np
from datetime import date

from risk_analytics_engine.metrics import calculate_volatility, calculate_drawdown, calculate_sharpe_ratio, calculate_sortino_ratio
from risk_analytics_engine.exceptions import InsufficientDataError
from risk_analytics_engine.helpers import convert_annual_rate_to_periodic

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

def test_calculate_sharpe_ratio_happy_path():
    """
    GIVEN a series of returns and a risk-free rate
    WHEN calculate_sharpe_ratio is called
    THEN it should return the correct annualized Sharpe Ratio.
    """
    # ARRANGE
    returns = pd.Series([3, 1, 5, 3]) # Mean=3, Stdev=1.633
    annual_rf_rate = 0.025 # 2.5%
    annualization_factor = 252
    
    periodic_rf_rate = convert_annual_rate_to_periodic(annual_rf_rate, annualization_factor)

    # ACT
    result = calculate_sharpe_ratio(returns, periodic_rf_rate, annualization_factor)

    # ASSERT
    # Manual calculation for verification
    returns_dec = returns / 100
    excess_returns = returns_dec - periodic_rf_rate
    mean_ex = excess_returns.mean()
    std_ex = excess_returns.std()
    expected_sharpe = (mean_ex / std_ex) * np.sqrt(annualization_factor)
    
    assert result == pytest.approx(expected_sharpe)

def test_calculate_sharpe_ratio_insufficient_data():
    """
    GIVEN a return series with fewer than two data points
    WHEN calculate_sharpe_ratio is called
    THEN it should raise an InsufficientDataError.
    """
    with pytest.raises(InsufficientDataError):
        calculate_sharpe_ratio(pd.Series([1.0]), 0.0, 252)

def test_calculate_sortino_ratio_happy_path():
    """
    GIVEN a series of returns and a MAR
    WHEN calculate_sortino_ratio is called
    THEN it should return the correct annualized Sortino Ratio.
    """
    # ARRANGE
    returns = pd.Series([3, 5, -2, 4, -1]) # MAR is 0%
    annualization_factor = 252
    
    # ACT
    result = calculate_sortino_ratio(returns, 0.0, annualization_factor)

    # ASSERT
    returns_dec = returns / 100
    downside_returns = returns_dec[returns_dec < 0]
    downside_dev = np.sqrt((downside_returns**2).sum() / len(returns))
    mean_return = returns_dec.mean()
    expected_sortino = (mean_return / downside_dev) * np.sqrt(annualization_factor)

    assert result == pytest.approx(expected_sortino)