# src/libs/performance-calculator-engine/src/performance_calculator_engine/calculator.py
import logging
from datetime import date
from decimal import Decimal, getcontext
from typing import List, Dict, Any

import pandas as pd
import calendar

from .constants import (
    BOD_CASHFLOW,
    BOD_MARKET_VALUE,
    DAILY_ROR_PCT,
    DATE,
    EOD_CASHFLOW,
    EOD_MARKET_VALUE,
    FEES,
    FINAL_CUMULATIVE_ROR_PCT,
    LONG_CUM_ROR_PCT,
    LONG_SHORT,
    METRIC_BASIS_GROSS,
    METRIC_BASIS_NET,
    NCTRL_1,
    NCTRL_2,
    NCTRL_3,
    NCTRL_4,
    NIP,
    PERF_RESET,
    PERIOD_TYPE_EXPLICIT,
    PERIOD_TYPE_MTD,
    PERIOD_TYPE_QTD,
    PERIOD_TYPE_YTD,
    SHORT_CUM_ROR_PCT,
    SIGN,
    TEMP_LONG_CUM_ROR_PCT,
    TEMP_SHORT_CUM_ROR_PCT,
)
from .exceptions import CalculationLogicError, InvalidInputDataError, MissingConfigurationError

logger = logging.getLogger(__name__)
getcontext().prec = 28


class PerformanceCalculator:
    """
    Performs complex, stateful time-weighted return calculations on a series of daily data.
    This engine is ported from the logic in the performanceAnalytics repository,
    and adapted for the portfolio-analytics-system's architecture and conventions.
    """
    def __init__(self, config: Dict[str, Any]):
        logger.info("Initializing PerformanceCalculator.")
        if not config:
            raise MissingConfigurationError("Calculator configuration cannot be empty.")

        self.metric_basis = config.get("metric_basis", METRIC_BASIS_NET)
        if self.metric_basis not in [METRIC_BASIS_NET, METRIC_BASIS_GROSS]:
            raise InvalidInputDataError(f"Invalid 'metric_basis': {self.metric_basis}.")

        self.period_type = config.get("period_type", PERIOD_TYPE_EXPLICIT)
        if self.period_type not in [PERIOD_TYPE_MTD, PERIOD_TYPE_QTD, PERIOD_TYPE_YTD, PERIOD_TYPE_EXPLICIT]:
            raise InvalidInputDataError(f"Invalid 'period_type': {self.period_type}.")

        self.performance_start_date = self._parse_date(config.get("performance_start_date"))
        self.report_start_date = self._parse_date(config.get("report_start_date"))
        self.report_end_date = self._parse_date(config.get("report_end_date"))

        if not self.performance_start_date or not self.report_end_date:
            raise MissingConfigurationError("'performance_start_date' and 'report_end_date' are required.")

        logger.info(f"Calculator configured for period {self.report_start_date} to {self.report_end_date} ({self.period_type}, {self.metric_basis})")

    def calculate_performance(self, daily_data_list: List[Dict[str, Any]]) -> pd.DataFrame:
        """
        Calculates daily performance metrics for a given list of time-series data.
        """
        if not daily_data_list:
            raise InvalidInputDataError("Input 'daily_data_list' cannot be empty.")

        df = self._prepare_dataframe(daily_data_list)
        if df.empty:
            return pd.DataFrame()

        self._initialize_calculated_columns(df)
        self._run_iterative_calculations(df)

        # Convert Decimal columns to float for easier consumption by APIs
        for col in df.select_dtypes(include=['object']).columns:
            if all(isinstance(x, Decimal) for x in df[col]):
                df[col] = df[col].astype(float)

        return df

    def _prepare_dataframe(self, daily_data_list: List[Dict[str, Any]]) -> pd.DataFrame:
        """Converts raw data list to a cleaned and typed pandas DataFrame."""
        try:
            df = pd.DataFrame(daily_data_list)
            numeric_cols = [BOD_MARKET_VALUE, EOD_MARKET_VALUE, BOD_CASHFLOW, EOD_CASHFLOW, FEES]
            for col in numeric_cols:
                df[col] = df[col].apply(Decimal)
            df[DATE] = pd.to_datetime(df[DATE]).dt.date
            return df[df[DATE] <= self.report_end_date].copy()
        except Exception as e:
            raise InvalidInputDataError(f"Failed to create or process DataFrame: {e}")

    def _initialize_calculated_columns(self, df: pd.DataFrame) -> None:
        """Initializes all columns that will be calculated during the iterative process."""
        df[NIP] = self._calculate_nip_vectorized(df)
        df["effective_period_start_date"] = df[DATE].apply(
            lambda x: self._get_effective_period_start_date(x)
        )
        df[DAILY_ROR_PCT] = self._calculate_daily_ror_vectorized(df)

        # Initialize remaining iterative columns
        for col in [SIGN, TEMP_LONG_CUM_ROR_PCT, TEMP_SHORT_CUM_ROR_PCT, LONG_CUM_ROR_PCT, SHORT_CUM_ROR_PCT, FINAL_CUMULATIVE_ROR_PCT]:
            df[col] = Decimal(0)
        for col in [NCTRL_1, NCTRL_2, NCTRL_3, NCTRL_4, PERF_RESET]:
            df[col] = 0
        df[LONG_SHORT] = ""

    def _run_iterative_calculations(self, df: pd.DataFrame) -> None:
        """
        The main stateful loop that calculates metrics for each day,
        depending on the results of the previous day.
        """
        # Convert to records for faster iteration
        records = df.to_dict('records')
        calculated_rows = []

        for i, current_row in enumerate(records):
            prev_day_calculated = calculated_rows[i - 1] if i > 0 else None
            
            # --- Perform Calculations ---
            current_row[SIGN] = self._calculate_sign(current_row, prev_day_calculated)
            current_row[TEMP_LONG_CUM_ROR_PCT] = self._calculate_temp_long_cum_ror(current_row, prev_day_calculated)
            current_row[TEMP_SHORT_CUM_ROR_PCT] = self._calculate_temp_short_cum_ror(current_row, prev_day_calculated)

            n1, n2, n3 = self._calculate_nctrls_1_2_3(current_row, records[i + 1] if i + 1 < len(records) else None)
            current_row[NCTRL_1], current_row[NCTRL_2], current_row[NCTRL_3] = n1, n2, n3
            
            current_row[NCTRL_4] = self._calculate_nctrl_4(current_row, prev_day_calculated)
            current_row[PERF_RESET] = 1 if any([n1, n2, n3, current_row[NCTRL_4]]) else 0

            long_cum_ror, short_cum_ror = self._calculate_long_short_cum_ror_final(current_row, prev_day_calculated, records[i + 1] if i + 1 < len(records) else None)
            current_row[LONG_CUM_ROR_PCT], current_row[SHORT_CUM_ROR_PCT] = long_cum_ror, short_cum_ror
            
            current_row[LONG_SHORT] = "S" if current_row[SIGN] == -1 else "L"

            current_row[FINAL_CUMULATIVE_ROR_PCT] = (
                (Decimal(1) + long_cum_ror / 100) * (Decimal(1) + short_cum_ror / 100) - Decimal(1)
            ) * 100

            calculated_rows.append(current_row)

        # Update original DataFrame with calculated values
        for col in df.columns:
            if col != 'index': # Avoid trying to assign the old index
                df[col] = [row[col] for row in calculated_rows]
        df.drop(columns=["effective_period_start_date"], inplace=True)


    # --- Helper & Vectorized Methods ---

    def _parse_date(self, date_val: Any) -> date | None:
        if isinstance(date_val, date): return date_val
        if isinstance(date_val, str):
            try: return datetime.strptime(date_val, "%Y-%m-%d").date()
            except ValueError: return None
        return None

    def _get_effective_period_start_date(self, row_date: date) -> date:
        effective_date = self.performance_start_date
        if self.period_type == PERIOD_TYPE_MTD:
            effective_date = date(row_date.year, row_date.month, 1)
        elif self.period_type == PERIOD_TYPE_QTD:
            quarter_month = (row_date.month - 1) // 3 * 3 + 1
            effective_date = date(row_date.year, quarter_month, 1)
        elif self.period_type == PERIOD_TYPE_YTD:
            effective_date = date(row_date.year, 1, 1)
        elif self.period_type == PERIOD_TYPE_EXPLICIT:
            effective_date = max(self.performance_start_date, self.report_start_date or self.performance_start_date)
        return max(effective_date, self.performance_start_date)

    def _calculate_nip_vectorized(self, df: pd.DataFrame) -> pd.Series:
        cond = (df[BOD_MARKET_VALUE] + df[BOD_CASHFLOW] + df[EOD_MARKET_VALUE] + df[EOD_CASHFLOW] == 0) & \
               (df[EOD_CASHFLOW] == -df[BOD_CASHFLOW])
        return cond.astype(int)

    def _calculate_daily_ror_vectorized(self, df: pd.DataFrame) -> pd.Series:
        numerator = df[EOD_MARKET_VALUE] - df[BOD_MARKET_VALUE] - df[BOD_CASHFLOW] - df[EOD_CASHFLOW]
        if self.metric_basis == METRIC_BASIS_NET:
            numerator += df[FEES]
        denominator = df[BOD_MARKET_VALUE] + df[BOD_CASHFLOW]
        
        daily_ror = pd.Series([Decimal(0)] * len(df), index=df.index)
        mask = (df[DATE] >= df["effective_period_start_date"]) & (denominator != 0)
        daily_ror[mask] = (numerator[mask] / denominator[mask]) * Decimal(100)
        return daily_ror

    # --- Iterative Calculation Logic Methods ---

    def _calculate_sign(self, current, prev):
        val_for_sign = current[BOD_MARKET_VALUE] + current[BOD_CASHFLOW]
        current_sign_val = Decimal(1) if val_for_sign > 0 else (Decimal(-1) if val_for_sign < 0 else Decimal(0))
        if not prev: return current_sign_val
        
        prev_sign = prev[SIGN]
        if current_sign_val != prev_sign and prev_sign != 0 and prev[PERF_RESET] != 1 and \
           prev[BOD_CASHFLOW] == 0 and prev[EOD_CASHFLOW] == 0:
            return prev_sign
        return current_sign_val
        
    def _calculate_temp_long_cum_ror(self, current, prev):
        if current[DATE] == current["effective_period_start_date"]: return current[DAILY_ROR_PCT]
        if current[SIGN] != 1: return Decimal(0)
        if not prev: return current[DAILY_ROR_PCT]
        
        prev_long_cum_ror = prev[LONG_CUM_ROR_PCT]
        if current[DAILY_ROR_PCT] == 0: return prev_long_cum_ror
        
        return ((Decimal(1) + prev_long_cum_ror / 100) * (Decimal(1) + current[DAILY_ROR_PCT] / 100 * current[SIGN]) - Decimal(1)) * 100

    def _calculate_temp_short_cum_ror(self, current, prev):
        if current[DATE] == current["effective_period_start_date"]: return current[DAILY_ROR_PCT]
        if current[SIGN] == 1: return Decimal(0)
        if not prev: return current[DAILY_ROR_PCT]

        prev_short_cum_ror = prev[SHORT_CUM_ROR_PCT]
        if current[DAILY_ROR_PCT] == 0: return prev_short_cum_ror
        
        return ((Decimal(1) + prev_short_cum_ror / 100) * (Decimal(1) + current[DAILY_ROR_PCT] / 100 * current[SIGN]) - Decimal(1)) * 100

    def _calculate_nctrls_1_2_3(self, current, next_row):
        next_bod_cf = next_row[BOD_CASHFLOW] if next_row else Decimal(0)
        next_date_beyond = next_row[DATE] > self.report_end_date if next_row and self.report_end_date else False
        
        cond = current[BOD_CASHFLOW] != 0 or next_bod_cf != 0 or current[EOD_CASHFLOW] != 0 or \
               current[DATE].day == calendar.monthrange(current[DATE].year, current[DATE].month)[1] or next_date_beyond
        
        n1 = 1 if current[TEMP_LONG_CUM_ROR_PCT] < -100 and cond else 0
        n2 = 1 if current[TEMP_SHORT_CUM_ROR_PCT] > 100 and cond else 0
        n3 = 1 if current[TEMP_SHORT_CUM_ROR_PCT] < -100 and current[TEMP_LONG_CUM_ROR_PCT] != 0 and cond else 0
        return n1, n2, n3

    def _calculate_nctrl_4(self, current, prev):
        if not prev: return 0
        
        if (prev[TEMP_LONG_CUM_ROR_PCT] <= -100 or prev[TEMP_SHORT_CUM_ROR_PCT] >= 100) and \
           (current[BOD_CASHFLOW] != 0 or prev[EOD_CASHFLOW] != 0):
            return 1
        return 0

    def _calculate_long_short_cum_ror_final(self, current, prev, next_row):
        prev_long_ror = prev[LONG_CUM_ROR_PCT] if prev else Decimal(0)
        prev_short_ror = prev[SHORT_CUM_ROR_PCT] if prev else Decimal(0)
        prev_nip = prev[NIP] if prev else 0

        if current[NIP] == 1:
            next_nip = next_row[NIP] if next_row else 0
            next_bod_cf = next_row[BOD_CASHFLOW] if next_row else Decimal(0)
            lookahead_reset = next_nip == 0 and next_bod_cf != 0 and (prev_long_ror <= -100 or prev_short_ror >= 100)
            
            if current[DATE] == current["effective_period_start_date"] or lookahead_reset:
                return Decimal(0), Decimal(0)
            return prev_long_ror, prev_short_ror

        if prev and prev_nip == 1 and current[BOD_CASHFLOW] == 0 and (prev_long_ror <= -100 or prev_short_ror >= 100):
             return Decimal(0), Decimal(0)
             
        return current[TEMP_LONG_CUM_ROR_PCT], current[TEMP_SHORT_CUM_ROR_PCT]