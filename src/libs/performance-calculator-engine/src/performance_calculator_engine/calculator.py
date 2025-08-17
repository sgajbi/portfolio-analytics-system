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
    
    def _get_sign(self, value):
        value = self._parse_decimal(value)
        if value > 0:
            return Decimal(1)
        elif value < 0:
            return Decimal(-1)
        else:
            return Decimal(0)

    def _is_eomonth(self, date_obj):
        return date_obj.day == calendar.monthrange(date_obj.year, date_obj.month)[1]

    def _calculate_nip_vectorized(self, df: pd.DataFrame) -> pd.Series:
        cond1 = (
            df[BEGIN_MARKET_VALUE_FIELD] + df[BOD_CASHFLOW_FIELD] + df[END_MARKET_VALUE_FIELD] + df[EOD_CASHFLOW_FIELD]
            == 0
        ) & (df[EOD_CASHFLOW_FIELD] == -df[BOD_CASHFLOW_FIELD].apply(self._get_sign))
        return cond1.astype(int)

    def _calculate_daily_ror_vectorized(self, df, effective_start_date_series):
        daily_ror = pd.Series([Decimal(0)] * len(df), index=df.index, dtype=object)

        condition = (df[PERF_DATE_FIELD] >= effective_start_date_series) & (
            df[BEGIN_MARKET_VALUE_FIELD] + df[BOD_CASHFLOW_FIELD] != 0
        )

        numerator = (
            df[END_MARKET_VALUE_FIELD] - df[BOD_CASHFLOW_FIELD] - df[BEGIN_MARKET_VALUE_FIELD] - df[EOD_CASHFLOW_FIELD]
        )
        if self.metric_basis == METRIC_BASIS_NET:
            numerator += df[MGMT_FEES_FIELD]

        denominator = abs(df[BEGIN_MARKET_VALUE_FIELD] + df[BOD_CASHFLOW_FIELD])
        ror_calc = (numerator / denominator * 100).where(denominator != 0, Decimal(0))
        daily_ror = daily_ror.mask(condition, ror_calc)
        return daily_ror
    
    def calculate_performance(self, daily_data_list):
        if not daily_data_list:
            raise InvalidInputDataError("Daily data list cannot be empty.")

        try:
            df = pd.DataFrame(daily_data_list)
        except Exception as e:
            raise InvalidInputDataError(f"Failed to create DataFrame from daily data: {e}")

        numeric_cols = [
            "Day", BEGIN_MARKET_VALUE_FIELD, BOD_CASHFLOW_FIELD,
            EOD_CASHFLOW_FIELD, MGMT_FEES_FIELD, END_MARKET_VALUE_FIELD,
        ]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = df[col].apply(self._parse_decimal)

        df[PERF_DATE_FIELD] = pd.to_datetime(df[PERF_DATE_FIELD], errors="coerce").dt.date
        if df[PERF_DATE_FIELD].isnull().any():
            raise InvalidInputDataError("One or more 'Perf. Date' values are invalid or missing.")

        # Determine effective start date for filtering
        overall_effective_report_start_date = self.report_start_date or self.performance_start_date
        df = df[df[PERF_DATE_FIELD] <= self.report_end_date].copy()
        if df.empty:
            return []

        # Initialize columns
        for col in [
            "sign", DAILY_ROR_PERCENT_FIELD, TEMP_LONG_CUM_ROR_PERCENT_FIELD,
            TEMP_SHORT_CUM_ROR_PERCENT_FIELD, LONG_CUM_ROR_PERCENT_FIELD,
            SHORT_CUM_ROR_PERCENT_FIELD, FINAL_CUMULATIVE_ROR_PERCENT_FIELD,
        ]:
            df[col] = Decimal(0)
        for col in [NCTRL_1_FIELD, NCTRL_2_FIELD, NCTRL_3_FIELD, NCTRL_4_FIELD, PERF_RESET_FIELD, NIP_FIELD]:
            df[col] = 0
        df[LONG_SHORT_FIELD] = ""

        # Vectorized calculations first
        df[NIP_FIELD] = self._calculate_nip_vectorized(df)
        
        # This logic is simplified for now but captures the period-based start date concept
        df["effective_period_start_date"] = df[PERF_DATE_FIELD].apply(
            lambda x: date(x.year, 1, 1) if self.period_type == PERIOD_TYPE_YTD else self.performance_start_date
        )
        df[DAILY_ROR_PERCENT_FIELD] = self._calculate_daily_ror_vectorized(df, df["effective_period_start_date"])

        # Iterative calculations for stateful logic
        calculated_rows = []
        for i in range(len(df)):
            row = df.iloc[i].to_dict()
            prev_row = calculated_rows[i - 1] if i > 0 else None
            
            # This is a simplified sequential calculation that mimics the intent of the original logic
            # for a typical case without resets. The full NCTRL/reset logic is complex and will be
            # added back based on more detailed test cases.
            if prev_row:
                prev_cumulative_factor = (Decimal(1) + prev_row[FINAL_CUMULATIVE_ROR_PERCENT_FIELD] / 100)
                current_daily_factor = (Decimal(1) + row[DAILY_ROR_PERCENT_FIELD] / 100)
                row[FINAL_CUMULATIVE_ROR_PERCENT_FIELD] = (prev_cumulative_factor * current_daily_factor - 1) * 100
            else:
                row[FINAL_CUMULATIVE_ROR_PERCENT_FIELD] = row[DAILY_ROR_PERCENT_FIELD]
            
            calculated_rows.append(row)

        final_df = pd.DataFrame(calculated_rows)
        
        # Filter again for the final report range
        final_df = final_df[final_df[PERF_DATE_FIELD] >= overall_effective_report_start_date].copy()

        # Convert Decimal columns to float for simpler JSON serialization
        for col in final_df.select_dtypes(include=['object']):
            if not final_df[col].empty and isinstance(final_df[col].iloc[0], Decimal):
                final_df[col] = final_df[col].astype(float)
        
        final_df[PERF_DATE_FIELD] = final_df[PERF_DATE_FIELD].astype(str)
        
        return final_df.to_dict(orient="records")