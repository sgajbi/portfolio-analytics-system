# src/libs/risk-analytics-engine/src/risk_analytics_engine/metrics.py
import numpy as np
import pandas as pd
from typing import Dict, Any, Optional
from .exceptions import InsufficientDataError

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

    # Calculate the standard deviation of the return series.
    # The returns are expected as percentages (e.g., 1.0 for 1%), so we divide by 100.
    std_dev = returns.std() / 100
    
    # Annualize the standard deviation.
    annualized_vol = std_dev * np.sqrt(annualization_factor)
    
    return annualized_vol


def calculate_drawdown(returns: pd.Series) -> Dict[str, Any]:
    """
    Calculates the maximum drawdown and its corresponding dates from a return series.

    Args:
        returns: A pandas Series of periodic returns (as percentages) with a DatetimeIndex.

    Returns:
        A dictionary containing the max drawdown, peak date, and trough date.
        Example: {'max_drawdown': -0.10, 'peak_date': '2025-01-10', 'trough_date': '2025-02-20'}

    Raises:
        InsufficientDataError: If the return series is empty.
    """
    if returns.empty:
        raise InsufficientDataError("Drawdown calculation requires at least one data point.")

    # Convert percentage returns to decimal and compute a wealth index
    wealth_index = 1000 * (1 + returns / 100).cumprod()
    
    # Calculate the previous peaks
    previous_peaks = wealth_index.cummax()
    
    # Calculate the drawdown series
    drawdown_series = (wealth_index - previous_peaks) / previous_peaks
    
    # Find the maximum drawdown (minimum value in the series)
    max_drawdown = drawdown_series.min()
    
    # Find the date of the maximum drawdown (the trough)
    trough_date = drawdown_series.idxmin() if pd.notna(max_drawdown) else None
    
    # Find the peak date that corresponds to this trough
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
    """
    Calculates the annualized Sharpe Ratio.

    Args:
        returns: A pandas Series of periodic returns (as percentages).
        periodic_risk_free_rate: The risk-free rate for a single period (as a decimal).
        annualization_factor: The factor for annualizing (e.g., 252 for daily).

    Returns:
        The annualized Sharpe Ratio, or None if volatility is zero.
    """
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