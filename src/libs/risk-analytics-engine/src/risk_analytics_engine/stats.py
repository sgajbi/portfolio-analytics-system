# src/libs/risk-analytics-engine/src/risk_analytics_engine/stats.py
import pandas as pd
from scipy.stats import skew, kurtosis

def calculate_skewness(returns: pd.Series) -> float:
    """
    Calculates the skewness of a return series.
    A measure of the asymmetry of the probability distribution.
    """
    # dropna() is important to handle potential missing values cleanly
    return skew(returns.dropna())

def calculate_kurtosis(returns: pd.Series) -> float:
    """
    Calculates the excess kurtosis of a return series.
    A measure of the "tailedness" of the probability distribution.
    scipy.stats.kurtosis calculates excess kurtosis (Kurtosis - 3).
    """
    return kurtosis(returns.dropna())