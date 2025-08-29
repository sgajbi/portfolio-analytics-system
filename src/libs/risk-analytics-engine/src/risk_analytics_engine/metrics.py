# src/libs/risk-analytics-engine/src/risk_analytics_engine/metrics.py
import numpy as np
import pandas as pd
from typing import Dict, Any, Optional
from scipy.stats import norm

from .exceptions import InsufficientDataError
from .stats import calculate_skewness, calculate_kurtosis

def calculate_volatility(
    returns: pd.Series,
    annualization_factor: int,
) -> float:
    """
    Calculates the annualized volatility (standard deviation) of a return series.

    Args:
        returns: A pandas Series of periodic returns (e.g., daily, weekly).
        annualization_factor: The factor to scale the volatility to an annual figure
                              (e.g., 252 for daily, 52 for weekly, 12 for monthly).

    Returns:
        The annualized volatility as a float.

    Raises:
        InsufficientDataError: If the return series has fewer than two data points.
    """
    if len(returns) < 2:
        raise InsufficientDataError("Volatility calculation requires at least two data points.")

    std_dev = returns.std() / 100
    annualized_vol = std_dev * np.sqrt(annualization_factor)
    return annualized_vol


def calculate_drawdown(returns: pd.Series) -> Dict[str, Any]:
    """
    Calculates the maximum drawdown and its corresponding dates from a return series.

    Args:
        returns: A pandas Series of periodic returns (as percentages) with a DatetimeIndex.

    Returns:
        A dictionary containing the max drawdown, peak date, and trough date.
    """
    if returns.empty:
        raise InsufficientDataError("Drawdown calculation requires at least one data point.")

    wealth_index = 1000 * (1 + returns / 100).cumprod()
    previous_peaks = wealth_index.cummax()
    drawdown_series = (wealth_index - previous_peaks) / previous_peaks
    max_drawdown = drawdown_series.min()
    trough_date = drawdown_series.idxmin() if pd.notna(max_drawdown) else None
    peak_date = wealth_index.loc[:trough_date].idxmax() if trough_date else None

    return {
        "max_drawdown": max_drawdown,
        "peak_date": peak_date.date() if peak_date else None,
        "trough_date": trough_date.date() if trough_date else None,
    }


def calculate_sharpe_ratio(
    returns: pd.Series,
    periodic_risk_free_rate: float,
    annualization_factor: int
) -> Optional[float]:
    """Calculates the annualized Sharpe Ratio."""
    if len(returns) < 2:
        raise InsufficientDataError("Sharpe Ratio requires at least two data points.")

    returns_decimal = returns / 100
    excess_returns = returns_decimal - periodic_risk_free_rate
    mean_excess_return = excess_returns.mean()
    std_dev_excess_return = excess_returns.std()

    if std_dev_excess_return == 0:
        return None

    sharpe_ratio = mean_excess_return / std_dev_excess_return
    return sharpe_ratio * np.sqrt(annualization_factor)


def calculate_sortino_ratio(
    returns: pd.Series,
    periodic_mar: float,
    annualization_factor: int
) -> Optional[float]:
    """Calculates the annualized Sortino Ratio."""
    if len(returns) < 2:
        raise InsufficientDataError("Sortino Ratio requires at least two data points.")

    returns_decimal = returns / 100
    excess_returns = returns_decimal - periodic_mar
    downside_returns = excess_returns[excess_returns < 0]
    downside_deviation = np.sqrt((downside_returns**2).sum() / len(returns))

    if downside_deviation == 0:
        return None

    mean_excess_return = excess_returns.mean()
    sortino_ratio = mean_excess_return / downside_deviation
    return sortino_ratio * np.sqrt(annualization_factor)


def calculate_beta(
    portfolio_returns: pd.Series,
    benchmark_returns: pd.Series
) -> Optional[float]:
    """Calculates the Beta of a portfolio relative to a benchmark."""
    if len(portfolio_returns) < 2 or len(benchmark_returns) < 2:
        raise InsufficientDataError("Beta calculation requires at least two data points for both series.")
    covariance = portfolio_returns.cov(benchmark_returns)
    variance = benchmark_returns.var()
    return covariance / variance if variance != 0 else None


def calculate_tracking_error(
    portfolio_returns: pd.Series,
    benchmark_returns: pd.Series,
    annualization_factor: int
) -> float:
    """Calculates the annualized Tracking Error."""
    if len(portfolio_returns) < 2:
        raise InsufficientDataError("Tracking Error requires at least two data points.")
    active_return = portfolio_returns - benchmark_returns
    return active_return.std() * np.sqrt(annualization_factor)


def calculate_information_ratio(
    portfolio_returns: pd.Series,
    benchmark_returns: pd.Series,
    annualization_factor: int
) -> Optional[float]:
    """Calculates the annualized Information Ratio."""
    if len(portfolio_returns) < 2:
        raise InsufficientDataError("Information Ratio requires at least two data points.")

    active_return = portfolio_returns - benchmark_returns
    mean_active_return = active_return.mean()
    tracking_error = active_return.std()

    if tracking_error == 0:
        return None
        
    annualized_mean_active = mean_active_return * annualization_factor
    annualized_tracking_error = tracking_error * np.sqrt(annualization_factor)
    return annualized_mean_active / annualized_tracking_error if annualized_tracking_error != 0 else None


def calculate_var(
    returns: pd.Series,
    confidence: float,
    method: str
) -> float:
    """
    Calculates the Value at Risk (VaR) for a given return series.
    Returns VaR as a positive number representing a loss (e.g., 2.5 for a 2.5% loss).
    """
    if returns.empty:
        raise InsufficientDataError("VaR calculation requires at least one data point.")
    
    alpha = 1 - confidence
    returns_dec = returns / 100

    if method == "HISTORICAL":
        var = -returns_dec.quantile(alpha)
    elif method == "GAUSSIAN":
        mean = returns_dec.mean()
        std = returns_dec.std()
        z_score = norm.ppf(alpha)
        var = -(mean + z_score * std)
    elif method == "CORNISH_FISHER":
        mean = returns_dec.mean()
        std = returns_dec.std()
        skew = calculate_skewness(returns_dec)
        kurt = calculate_kurtosis(returns_dec)
        z_score = norm.ppf(alpha)
        
        # Cornish-Fisher adjustment to the Z-score
        z_cf = (z_score + 
                (z_score**2 - 1) * skew / 6 + 
                (z_score**3 - 3 * z_score) * kurt / 24 - 
                (2 * z_score**3 - 5 * z_score) * skew**2 / 36)
        
        var = -(mean + z_cf * std)
    else:
        raise ValueError(f"Unknown VaR method: {method}")

    return var * 100 # Return as a percentage


def calculate_expected_shortfall(
    returns: pd.Series,
    confidence: float,
    var_value: float
) -> float:
    """
    Calculates the Expected Shortfall (ES or CVaR).
    Returns ES as a positive number representing a loss.
    """
    var_decimal = var_value / 100
    returns_dec = returns / 100
    
    # ES is the average of all returns that are worse than the VaR
    tail_losses = returns_dec[returns_dec < -var_decimal]
    
    if tail_losses.empty:
        return var_value # If no losses are beyond VaR, ES is VaR itself.

    return -tail_losses.mean() * 100