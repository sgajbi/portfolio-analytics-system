# tests/unit/libs/risk-analytics-engine/test_metrics.py
import pytest
import pandas as pd
import numpy as np
from datetime import date

from risk_analytics_engine.metrics import (
    calculate_volatility, calculate_drawdown, calculate_sharpe_ratio,
    calculate_sortino_ratio, calculate_beta, calculate_tracking_error,
    calculate_information_ratio, calculate_var, calculate_expected_shortfall
)
from risk_analytics_engine.exceptions import InsufficientDataError
from risk_analytics_engine.helpers import convert_annual_rate_to_periodic

def test_calculate_volatility_happy_path():
    returns = pd.Series([-1.0, 3.0, -1.0, 3.0])
    annualization_factor = 252
    result = calculate_volatility(returns, annualization_factor)
    expected_std_dev = returns.std()
    expected_volatility = (expected_std_dev / 100) * np.sqrt(annualization_factor)
    assert result == pytest.approx(expected_volatility)

def test_calculate_volatility_raises_for_insufficient_data():
    with pytest.raises(InsufficientDataError):
        calculate_volatility(pd.Series([5.0]), 252)
    with pytest.raises(InsufficientDataError):
        calculate_volatility(pd.Series([], dtype=float), 252)

def test_calculate_drawdown_happy_path():
    dates = pd.to_datetime(["2025-01-01", "2025-01-02", "2025-01-03", "2025-01-04", "2025-01-05"])
    returns = pd.Series([5.0, -2.0, 3.0, -4.0, 2.0], index=dates)
    result = calculate_drawdown(returns)
    assert result["max_drawdown"] == pytest.approx(-0.04)
    assert result["peak_date"] == date(2025, 1, 3)
    assert result["trough_date"] == date(2025, 1, 4)

def test_calculate_drawdown_raises_for_insufficient_data():
    with pytest.raises(InsufficientDataError):
        calculate_drawdown(pd.Series([], dtype=float))

def test_calculate_sharpe_ratio_happy_path():
    returns = pd.Series([3, 1, 5, 3])
    annual_rf_rate = 0.025
    annualization_factor = 252
    periodic_rf_rate = convert_annual_rate_to_periodic(annual_rf_rate, annualization_factor)
    result = calculate_sharpe_ratio(returns, periodic_rf_rate, annualization_factor)
    returns_dec = returns / 100
    excess_returns = returns_dec - periodic_rf_rate
    mean_ex = excess_returns.mean()
    std_ex = excess_returns.std()
    expected_sharpe = (mean_ex / std_ex) * np.sqrt(annualization_factor)
    assert result == pytest.approx(expected_sharpe)

def test_calculate_sharpe_ratio_insufficient_data():
    with pytest.raises(InsufficientDataError):
        calculate_sharpe_ratio(pd.Series([1.0]), 0.0, 252)

def test_calculate_sortino_ratio_happy_path():
    returns = pd.Series([3, 5, -2, 4, -1])
    annualization_factor = 252
    result = calculate_sortino_ratio(returns, 0.0, annualization_factor)
    returns_dec = returns / 100
    downside_returns = returns_dec[returns_dec < 0]
    downside_dev = np.sqrt((downside_returns**2).sum() / len(returns))
    mean_return = returns_dec.mean()
    expected_sortino = (mean_return / downside_dev) * np.sqrt(annualization_factor)
    assert result == pytest.approx(expected_sortino)

def test_benchmark_metrics():
    portfolio_returns = pd.Series([1.1, 1.5, 2.0, 1.8, 0.5]) / 100
    benchmark_returns = pd.Series([1.0, 1.2, 1.8, 1.5, 0.3]) / 100
    annualization_factor = 252
    
    beta = calculate_beta(portfolio_returns, benchmark_returns)
    tracking_error = calculate_tracking_error(portfolio_returns, benchmark_returns, annualization_factor)
    info_ratio = calculate_information_ratio(portfolio_returns, benchmark_returns, annualization_factor)
    
    expected_beta = portfolio_returns.cov(benchmark_returns) / benchmark_returns.var()
    assert beta == pytest.approx(expected_beta)
    
    active_return = portfolio_returns - benchmark_returns
    expected_te = active_return.std() * np.sqrt(annualization_factor)
    assert tracking_error == pytest.approx(expected_te)
    
    expected_ir = (active_return.mean() * annualization_factor) / expected_te
    assert info_ratio == pytest.approx(expected_ir)

def test_calculate_var_and_es():
    """Tests VaR and ES calculations across different methods."""
    # Arrange: A skewed distribution to highlight differences between methods
    returns = pd.Series([-5, -2, -1, 0, 1, 1, 2, 2, 3, 10])
    confidence = 0.95 # We expect the 5th percentile loss

    # Act
    var_hist = calculate_var(returns, confidence, "HISTORICAL")
    es_hist = calculate_expected_shortfall(returns, confidence, var_hist)
    
    var_gauss = calculate_var(returns, confidence, "GAUSSIAN")
    var_cf = calculate_var(returns, confidence, "CORNISH_FISHER")

    # Assert
    # Historical VaR is the 5th percentile. Pandas interpolates between -5 and -2.
    # The 0.05 quantile is -3.65. VaR is the positive loss, so 3.65.
    assert var_hist == pytest.approx(3.65)
    
    # ES is the average of returns worse than VaR. Only -5 is worse than -3.65.
    assert es_hist == pytest.approx(5.0)

    # Gaussian VaR
    mean = returns.mean() / 100
    std = returns.std() / 100
    z_score = -1.64485
    expected_gauss_var = -(mean + z_score * std) * 100
    assert var_gauss == pytest.approx(expected_gauss_var)

    # Cornish-Fisher should be different from Gaussian due to skew/kurtosis
    assert var_cf != pytest.approx(var_gauss)