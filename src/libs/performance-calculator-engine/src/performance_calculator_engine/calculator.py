# src/libs/performance-calculator-engine/src/performance_calculator_engine/calculator.py
import logging
from decimal import Decimal, getcontext
from typing import Dict, Any

from .constants import (
    METRIC_BASIS_GROSS,
    METRIC_BASIS_NET
)
from .exceptions import CalculationLogicError

logger = logging.getLogger(__name__)

# Set precision for all Decimal operations in this module
getcontext().prec = 28

class PerformanceEngine:
    """
    A stateless engine for calculating daily performance metrics.
    """
    @staticmethod
    def calculate_daily_metrics(
        current_day_ts: Dict[str, Any],
        previous_day_ts: Dict[str, Any] = None
    ) -> Dict[str, Decimal]:
        """
        Calculates Net and Gross daily returns from a single day's time-series data.

        Args:
            current_day_ts: A dictionary-like object representing the portfolio_timeseries row for the current day.
            previous_day_ts: A dictionary-like object for the previous day, used for BOD Market Value.

        Returns:
            A dictionary containing calculated 'net_return' and 'gross_return'.
        """
        try:
            bod_market_value = Decimal(previous_day_ts['eod_market_value']) if previous_day_ts else Decimal(0)
            eod_market_value = Decimal(current_day_ts['eod_market_value'])
            bod_cashflow = Decimal(current_day_ts['bod_cashflow'])
            eod_cashflow = Decimal(current_day_ts['eod_cashflow'])
            fees = Decimal(current_day_ts['fees'])
            
            # Denominator for TWR is the same for both Net and Gross
            # It's Beginning Value + Weighted Cashflows. For daily, we assume mid-period cashflow for simplicity.
            # A more precise implementation would weight BOD and EOD cashflows.
            # Using Modified Dietz: Denominator = BOD_MV + Net Cashflow * Weight (here, 1 for full period)
            net_cashflow = bod_cashflow + eod_cashflow
            denominator = bod_market_value + net_cashflow

            if denominator.is_zero():
                return {
                    METRIC_BASIS_NET: Decimal(0),
                    METRIC_BASIS_GROSS: Decimal(0)
                }

            # Numerator = Change in Market Value - Net Cashflow
            change_in_mv = eod_market_value - bod_market_value
            
            # Gross Return calculation (before fees)
            gross_profit_loss = change_in_mv - net_cashflow
            gross_return = (gross_profit_loss / denominator) * 100

            # Net Return calculation (after fees)
            net_profit_loss = gross_profit_loss - fees
            net_return = (net_profit_loss / denominator) * 100

            return {
                METRIC_BASIS_NET: net_return,
                METRIC_BASIS_GROSS: gross_return
            }

        except (KeyError, TypeError) as e:
            logger.error(f"Input time-series data is missing required fields: {e}")
            raise CalculationLogicError(f"Input time-series data is missing required fields: {e}")