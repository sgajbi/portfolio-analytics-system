# src/libs/performance-calculator-engine/src/performance_calculator_engine/constants.py

# --- Input Field Names (from portfolio_timeseries table) ---
DATE = "date"
BOD_MARKET_VALUE = "bod_market_value"
EOD_MARKET_VALUE = "eod_market_value"
BOD_CASHFLOW = "bod_cashflow"
EOD_CASHFLOW = "eod_cashflow"
FEES = "fees"

# --- Intermediate & Output Field Names (ported from performanceAnalytics logic) ---
SIGN = "sign"
DAILY_ROR_PCT = "daily_ror_pct"
TEMP_LONG_CUM_ROR_PCT = "temp_long_cum_ror_pct"
TEMP_SHORT_CUM_ROR_PCT = "temp_short_cum_ror_pct"
NCTRL_1 = "nctrl_1"
NCTRL_2 = "nctrl_2"
NCTRL_3 = "nctrl_3"
NCTRL_4 = "nctrl_4"
PERF_RESET = "perf_reset"
NIP = "nip"
LONG_CUM_ROR_PCT = "long_cum_ror_pct"
SHORT_CUM_ROR_PCT = "short_cum_ror_pct"
LONG_SHORT = "long_short"
FINAL_CUMULATIVE_ROR_PCT = "final_cumulative_ror_pct"

# --- Configuration Values ---
METRIC_BASIS_NET = "NET"
METRIC_BASIS_GROSS = "GROSS"