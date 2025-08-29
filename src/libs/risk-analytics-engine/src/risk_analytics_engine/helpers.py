# src/libs/risk-analytics-engine/src/risk_analytics_engine/helpers.py
import numpy as np

def convert_annual_rate_to_periodic(
    annual_rate: float,
    periods_per_year: int
) -> float:
    """
    Converts an annualized rate to a periodic rate.

    Args:
        annual_rate: The rate expressed as an annual decimal (e.g., 0.02 for 2%).
        periods_per_year: The number of periods in a year (e.g., 252 for daily).

    Returns:
        The periodic rate as a decimal.
    """
    if periods_per_year <= 0:
        return 0.0
    # Formula for de-compounding: (1 + R_annual)^(1/k) - 1
    return (1 + annual_rate)**(1 / periods_per_year) - 1