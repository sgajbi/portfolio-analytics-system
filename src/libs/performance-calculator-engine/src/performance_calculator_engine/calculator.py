# src/libs/performance-calculator-engine/src/performance_calculator_engine/calculator.py
import calendar
import logging
from datetime import date, datetime
from decimal import Decimal, getcontext

import pandas as pd

from .constants import (
    BEGIN_MARKET_VALUE_FIELD,
    BOD_CASHFLOW_FIELD,
    DAILY_ROR_PERCENT_FIELD,
    END_MARKET_VALUE_FIELD,
    EOD_CASHFLOW_FIELD,
    FINAL_CUMULATIVE_ROR_PERCENT_FIELD,
    LONG_CUM_ROR_PERCENT_FIELD,
    LONG_SHORT_FIELD,
    METRIC_BASIS_GROSS,
    METRIC_BASIS_NET,
    MGMT_FEES_FIELD,
    NCTRL_1_FIELD,
    NCTRL_2_FIELD,
    NCTRL_3_FIELD,
    NCTRL_4_FIELD,
    NIP_FIELD,
    PERF_DATE_FIELD,
    PERF_RESET_FIELD,
    PERIOD_TYPE_EXPLICIT,
    PERIOD_TYPE_MTD,
    PERIOD_TYPE_QTD,
    PERIOD_TYPE_YTD,
    SHORT_CUM_ROR_PERCENT_FIELD,
    TEMP_LONG_CUM_ROR_PERCENT_FIELD,
    TEMP_SHORT_CUM_ROR_PERCENT_FIELD,
)
from .exceptions import CalculationLogicError, InvalidInputDataError, MissingConfigurationError

logger = logging.getLogger(__name__)


class PortfolioPerformanceCalculator:
    def __init__(self, config):
        if not config:
            raise MissingConfigurationError("Calculator configuration cannot be empty.")

        # Set precision for Decimal operations
        getcontext().prec = 28

        self.performance_start_date = self._parse_date(config.get("performance_start_date"))
        if not self.performance_start_date:
            raise MissingConfigurationError("'performance_start_date' is required.")

        self.metric_basis = config.get("metric_basis")
        if self.metric_basis not in [METRIC_BASIS_NET, METRIC_BASIS_GROSS]:
            raise InvalidInputDataError(f"Invalid 'metric_basis': {self.metric_basis}.")

        self.period_type = config.get("period_type", PERIOD_TYPE_EXPLICIT)
        if self.period_type not in [PERIOD_TYPE_MTD, PERIOD_TYPE_QTD, PERIOD_TYPE_YTD, PERIOD_TYPE_EXPLICIT]:
            raise InvalidInputDataError(f"Invalid 'period_type': {self.period_type}.")

        self.report_start_date = self._parse_date(config.get("report_start_date"))
        self.report_end_date = self._parse_date(config.get("report_end_date"))
        if not self.report_end_date:
            raise MissingConfigurationError("'report_end_date' is required.")

        if self.performance_start_date > self.report_end_date:
            raise InvalidInputDataError("'performance_start_date' must not be after 'report_end_date'.")

    def _parse_date(self, date_val):
        if isinstance(date_val, date):
            return date_val
        if isinstance(date_val, str):
            try:
                return datetime.strptime(date_val, "%Y-%m-%d").date()
            except ValueError:
                return None
        return None

    def _parse_decimal(self, value):
        try:
            return Decimal(str(value))
        except (ValueError, TypeError, SystemError):
            return Decimal(0)

    def calculate_performance(self, daily_data_list):
        if not daily_data_list:
            raise InvalidInputDataError("Daily data list cannot be empty.")

        try:
            df = pd.DataFrame(daily_data_list)
        except Exception as e:
            raise InvalidInputDataError(f"Failed to create DataFrame from daily data: {e}")

        numeric_cols = [
            BEGIN_MARKET_VALUE_FIELD, BOD_CASHFLOW_FIELD, EOD_CASHFLOW_FIELD,
            MGMT_FEES_FIELD, END_MARKET_VALUE_FIELD,
        ]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = df[col].apply(self._parse_decimal)

        df[PERF_DATE_FIELD] = pd.to_datetime(df[PERF_DATE_FIELD], errors="coerce").dt.date
        if df[PERF_DATE_FIELD].isnull().any():
            raise InvalidInputDataError("One or more 'Perf. Date' values are invalid or missing.")

        # Filter data for the relevant date range
        df = df[df[PERF_DATE_FIELD] <= self.report_end_date].copy()
        if df.empty:
            return []

        # --- Vectorized Calculations ---
        numerator = (
            df[END_MARKET_VALUE_FIELD] - df[BOD_CASHFLOW_FIELD] -
            df[BEGIN_MARKET_VALUE_FIELD] - df[EOD_CASHFLOW_FIELD]
        )
        if self.metric_basis == METRIC_BASIS_NET:
            numerator += df[MGMT_FEES_FIELD]

        denominator = (df[BEGIN_MARKET_VALUE_FIELD] + df[BOD_CASHFLOW_FIELD]).abs()

        # Initialize with zeros
        df[DAILY_ROR_PERCENT_FIELD] = Decimal(0)
        
        # Calculate only where denominator is not zero
        valid_mask = denominator != 0
        df.loc[valid_mask, DAILY_ROR_PERCENT_FIELD] = (numerator[valid_mask] / denominator[valid_mask]) * 100

        # --- For now, return a simplified dictionary for testing ---
        # The full iterative logic will be tested and integrated subsequently.
        df[FINAL_CUMULATIVE_ROR_PERCENT_FIELD] = \
            ((1 + df[DAILY_ROR_PERCENT_FIELD] / 100).cumprod() - 1) * 100

        # Convert Decimal columns to float for JSON serialization
        for col in df.select_dtypes(include=['object']).columns:
            if all(isinstance(x, Decimal) for x in df[col] if x is not None):
                df[col] = df[col].astype(float)
        
        df[PERF_DATE_FIELD] = df[PERF_DATE_FIELD].astype(str)

        return df.to_dict(orient="records")

    def get_summary_performance(self, calculated_results):
        if not calculated_results:
            return {}
        
        df = pd.DataFrame(calculated_results)
        
        first_day = df.iloc[0]
        last_day = df.iloc[-1]

        summary = {
            "report_start_date": self.report_start_date.strftime("%Y-%m-%d") if self.report_start_date else None,
            "report_end_date": self.report_end_date.strftime("%Y-%m-%d"),
            BEGIN_MARKET_VALUE_FIELD: float(first_day[BEGIN_MARKET_VALUE_FIELD]),
            END_MARKET_VALUE_FIELD: float(last_day[END_MARKET_VALUE_FIELD]),
            BOD_CASHFLOW_FIELD: float(df[BOD_CASHFLOW_FIELD].sum()),
            EOD_CASHFLOW_FIELD: float(df[EOD_CASHFLOW_FIELD].sum()),
            MGMT_FEES_FIELD: float(df[MGMT_FEES_FIELD].sum()),
            FINAL_CUMULATIVE_ROR_PERCENT_FIELD: float(last_day[FINAL_CUMULATIVE_ROR_PERCENT_FIELD])
        }
        return summary