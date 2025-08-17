# src/libs/performance-calculator-engine/src/performance_calculator_engine/calculator.py
import logging
from decimal import Decimal
from typing import List, Dict, Any

import pandas as pd

from .constants import (
    BOD_CASHFLOW,
    BOD_MARKET_VALUE,
    DAILY_ROR_PCT,
    DATE,
    EOD_CASHFLOW,
    EOD_MARKET_VALUE,
    FEES,
    METRIC_BASIS_GROSS,
    METRIC_BASIS_NET,
)
from .exceptions import CalculationLogicError, InvalidInputDataError

logger = logging.getLogger(__name__)


class PerformanceCalculator:
    """
    A stateless engine for calculating daily performance metrics from time-series data.
    It uses a vectorized approach for efficiency where possible.
    """

    def __init__(self, metric_basis: str = METRIC_BASIS_NET):
        if metric_basis not in [METRIC_BASIS_NET, METRIC_BASIS_GROSS]:
            raise InvalidInputDataError(
                f"Invalid 'metric_basis': {metric_basis}. Must be '{METRIC_BASIS_NET}' or '{METRIC_BASIS_GROSS}'."
            )
        self.metric_basis = metric_basis
        logger.info(f"PerformanceCalculator initialized with metric_basis: {self.metric_basis}")

    def calculate_performance(self, daily_data_list: List[Dict[str, Any]]) -> pd.DataFrame:
        """
        Calculates daily performance metrics for a given list of time-series data.

        Args:
            daily_data_list: A list of dictionaries, where each dictionary
                             represents a row of portfolio_timeseries data.

        Returns:
            A pandas DataFrame containing the original data plus calculated columns.
        """
        if not daily_data_list:
            raise InvalidInputDataError("Input 'daily_data_list' cannot be empty.")

        try:
            df = pd.DataFrame(daily_data_list)
            # Convert numeric columns to Decimal for precision
            for col in [BOD_MARKET_VALUE, EOD_MARKET_VALUE, BOD_CASHFLOW, EOD_CASHFLOW, FEES]:
                df[col] = df[col].apply(Decimal)
        except Exception as e:
            raise InvalidInputDataError(f"Failed to create DataFrame from daily data: {e}")

        # --- Main Calculation Flow ---
        df[DAILY_ROR_PCT] = self._calculate_daily_ror_vectorized(df)

        return df

    def _calculate_daily_ror_vectorized(self, df: pd.DataFrame) -> pd.Series:
        """
        Vectorized calculation of 'Daily ROR %' (Rate of Return).
        The formula is similar to Modified Dietz, accounting for beginning market value,
        cash flows (BOD and EOD), and fees (if metric_basis is NET).

        Args:
            df (pd.DataFrame): The DataFrame containing daily portfolio data.

        Returns:
            A pd.Series containing the calculated daily ROR percentages as Decimals.
        """
        # Numerator = Change in Market Value - Net Cashflow
        # (For NET basis, fees are subtracted from profit, so they are added back here as they are negative)
        change_in_mv = df[EOD_MARKET_VALUE] - df[BOD_MARKET_VALUE]
        net_cashflow = df[BOD_CASHFLOW] + df[EOD_CASHFLOW]

        numerator = change_in_mv - net_cashflow
        if self.metric_basis == METRIC_BASIS_NET:
            numerator = numerator + df[FEES]  # Fees are typically negative, so adding them reduces the gain

        # Denominator = BOD_MV + BOD_CF (approximating weighted cashflow)
        denominator = df[BOD_MARKET_VALUE] + df[BOD_CASHFLOW]

        # Calculate RoR, handling division by zero
        daily_ror = pd.Series([Decimal(0)] * len(df), index=df.index, dtype=object)
        non_zero_denom_mask = denominator != 0
        
        # Perform calculation only on rows where the denominator is not zero
        daily_ror[non_zero_denom_mask] = (
            (numerator[non_zero_denom_mask] / denominator[non_zero_denom_mask]) * Decimal(100)
        )

        return daily_ror