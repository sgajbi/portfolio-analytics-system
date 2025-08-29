# RFC 007: Risk Analytics APIs (Volatility, Drawdown, Sharpe, Sortino, Beta, VaR)

  * **Date:** 2025-08-29
  * **Services Affected:** `query-service`, `libs`
  * **Status:** **Proposed** (was: Draft)

## 1\. Summary (TL;DR)

This RFC proposes adding on-the-fly, portfolio-level risk analytics to `query-service`, computed from the same daily portfolio time-series and return engine already used by the TWR/MWR endpoints. We will introduce a reusable `libs/risk-analytics-engine` for the core algorithms and a new query endpoint that mirrors existing architectural patterns (DTOs → service → repository → FastAPI router). All metrics will be configurable (e.g., frequency, annualization, risk-free source, VaR confidence), robust to data irregularities, and aligned with industry best practices.

This implementation will reuse the `PerformanceRepository` to fetch `PortfolioTimeseries` and the `PerformanceCalculator` to generate the daily return series (`DAILY_ROR_PCT`), ensuring complete consistency with existing TWR calculations.

## 2\. Goals & Non-Goals

### Goals

  * Provide key portfolio-level risk metrics: **volatility**, **drawdown & max drawdown**, **Sharpe ratio**, **Sortino ratio**, **beta**, **tracking error**, **information ratio** (vs. benchmark), and **Value at Risk (VaR)** (historical, Gaussian, Cornish-Fisher methods).
  * Compute all metrics dynamically in `query-service` with no new data persistence.
  * Encapsulate all financial algorithms in a new, shared library: **`libs/risk-analytics-engine`**, mirroring the structure of `performance-calculator-engine`.
  * Ensure all calculation parameters (periods, frequency, annualization factors, risk-free rates, VaR confidence levels) are configurable per-request.

### Non-Goals

  * No changes to data ingestion, valuation, or time-series generation pipelines.
  * No persistence of risk metric outputs; all responses are computed on demand.
  * Rolling window calculations (e.g., 60-day rolling Sharpe ratio) are deferred to a future version (v2).

## 3\. Design Overview

### 3.1. New Library: `libs/risk-analytics-engine`

We will create a new, self-contained library for all risk calculations.

**Structure:**

```
src/libs/risk-analytics-engine/
  └── src/risk_analytics_engine/
        ├── __init__.py
        ├── constants.py         # Field names, defaults (e.g., annualization factors)
        ├── exceptions.py        # Custom exceptions (e.g., InsufficientDataError)
        ├── helpers.py           # Reusable helpers (e.g., annualization)
        ├── metrics.py           # Top-level functions for each metric
        └── stats.py             # Core statistical kernels (skew, kurtosis, etc.)
```

This structure is consistent with `performance-calculator-engine` and promotes code reuse and testability.

### 3.2. API Shape (`query-service`)

To maintain simplicity and efficiency for v1, we will implement a single, powerful multi-metric endpoint.

  * `POST /portfolios/{portfolio_id}/risk`

This endpoint will accept a request body specifying multiple periods and multiple metrics, calculating them all in a single pass. Individual endpoints (e.g., `/risk/volatility`) are deferred to v2 as they offer little benefit over a well-designed multi-metric request.

A new router will be created at `src/services/query_service/app/routers/risk.py` and registered in `main.py`, following the conventions of `performance.py`.

### 3.3. Data Transfer Objects (DTOs)

A new file, `src/services/query_service/app/dtos/risk_dto.py`, will be created. It will follow the established discriminated union pattern for period definitions.

**Refinement:** The VaR options will be defined in a strongly-typed `VaROptions` model instead of a generic `Dict[str, Any]` to improve validation, code completion, and API documentation.

```python
# app/dtos/risk_dto.py

# --- Reused from performance_dto.py ---
# ExplicitPeriod, YearPeriod, StandardPeriod

from .performance_dto import PerformanceRequestPeriod # Reusing for consistency

# --- New DTOs ---
class RiskRequestScope(BaseModel):
    as_of_date: date = Field(default_factory=date.today)
    reporting_currency: Optional[str] = None
    net_or_gross: Literal["NET", "GROSS"] = "NET"

class VaROptions(BaseModel):
    method: Literal["HISTORICAL", "GAUSSIAN", "CORNISH_FISHER"] = "HISTORICAL"
    confidence: float = Field(0.99, gt=0, lt=1)
    horizon_days: int = Field(1, gt=0)
    include_expected_shortfall: bool = True

class RiskOptions(BaseModel):
    frequency: Literal["DAILY", "WEEKLY", "MONTHLY"] = "DAILY"
    annualization_factor: Optional[int] = None
    use_log_returns: bool = False
    risk_free_mode: Literal["ZERO", "ANNUAL_RATE"] = "ZERO"
    risk_free_annual_rate: Optional[float] = Field(None, ge=0)
    mar_annual_rate: float = Field(0.0, ge=0, description="Minimum Acceptable Return for Sortino Ratio")
    benchmark_security_id: Optional[str] = None
    var: VaROptions = Field(default_factory=VaROptions)

class RiskRequest(BaseModel):
    scope: RiskRequestScope
    periods: List[PerformanceRequestPeriod]
    metrics: List[Literal[
        "VOLATILITY", "DRAWDOWN", "SHARPE", "SORTINO",
        "BETA", "TRACKING_ERROR", "INFORMATION_RATIO", "VAR"
    ]]
    options: RiskOptions = Field(default_factory=RiskOptions)

# --- Response DTOs (Sketch) ---
class RiskValue(BaseModel):
    value: Optional[float] = None
    details: Optional[Dict[str, Any]] = None # For drawdown dates, VaR ES, etc.

class RiskPeriodResult(BaseModel):
    start_date: date
    end_date: date
    metrics: Dict[str, RiskValue]

class RiskResponse(BaseModel):
    scope: RiskRequestScope
    results: Dict[str, RiskPeriodResult]
```

### 3.4. Service Layer (`risk_service.py`)

A new `src/services/query_service/app/services/risk_service.py` will orchestrate the logic:

1.  **Resolve Periods:** Reuse `performance_calculator_engine.helpers.resolve_period`.
2.  **Fetch Data:** Determine the union of all date ranges and make a single call to `PerformanceRepository.get_portfolio_timeseries_for_range` for the portfolio's current epoch.
3.  **Fetch Benchmark/FX Data (if needed):** If `benchmark_security_id` is provided, fetch its price history and any required FX rates using existing repositories.
4.  **Align Time Series:** Convert all time series (portfolio, benchmark) to the `reporting_currency`. Date-align the portfolio and benchmark return series using an **inner join** to ensure calculations only occur on days where both have data.
5.  **Calculate Base Returns:** Instantiate `PerformanceCalculator` once to get the primary daily return `pd.DataFrame`.
6.  **Compute Metrics:** For each period, slice the DataFrame, resample by frequency if necessary, and call the appropriate functions from the `risk-analytics-engine`.
7.  **Assemble Response:** Build the `RiskResponse` DTO.

## 4\. Design Decisions (Resolving Open Questions)

1.  **Tracking Error & Information Ratio:** These will be included in v1. The required components (benchmark returns, portfolio excess returns) are already needed for Beta, making these additions low-effort and high-value.
2.  **Currency Conversion for Benchmarks:** The `risk_service` will be responsible for this. All external time series (e.g., benchmark prices) will be converted to the `reporting_currency` specified in the request scope *before* returns are calculated and passed to the risk engine. This ensures all inputs operate in a consistent currency domain.

## 5\. Algorithms

All calculations will operate on a `pd.Series` of arithmetic returns, converted to decimals (`0.01` for `1%`) internally.

  * **Volatility ($\\sigma$):** Sample standard deviation of periodic returns, annualized with `sqrt(k)` where `k` is the number of periods in a year (e.g., 252 for daily).
  * **Drawdown:** Calculated from a wealth index `WI_t = WI_{t-1} * (1 + r_t)`. The drawdown at time `t` is `(WI_t - cummax(WI_t)) / cummax(WI_t)`. Max drawdown is the minimum of this series. The response will also include the peak date, trough date, and recovery date.
  * **Sharpe Ratio:** `(Mean(r_p) - r_f) / Stdev(r_p)`, annualized by multiplying by `sqrt(k)`.
  * **Sortino Ratio:** `(Mean(r_p) - MAR) / DownsideDeviation(r_p)`, annualized by multiplying by `sqrt(k)`.
  * **Beta ($\\beta$):** `Cov(r_p, r_b) / Var(r_b)`.
  * **Tracking Error:** `Stdev(r_p - r_b)`, annualized with `sqrt(k)`.
  * **Information Ratio:** `(Mean(r_p) - Mean(r_b)) / TrackingError`.
  * **Value at Risk (VaR):**
      * **Historical:** Empirical quantile of the return distribution.
      * **Gaussian:** `μ + z * σ`, using sample mean and standard deviation.
      * **Cornish-Fisher:** Adjusts the Gaussian z-score for skewness and kurtosis.
      * **Horizon Scaling:** The square-root-of-time rule (`VaR(T) = VaR(1) * sqrt(T)`) will be used, with the clear documentation that this assumes returns are i.i.d. (independent and identically distributed).
      * **Expected Shortfall (ES/CVaR):** The average of losses in the tail beyond the VaR threshold.

## 6\. Observability

We will add the following Prometheus metrics in `risk_service.py`:

  * `risk_metric_requested_total`: A `Counter` to track how often each risk metric is requested. Labels: `metric_name`.
  * `risk_metric_duration_seconds`: A `Histogram` to measure the calculation time for each individual metric. Labels: `metric_name`.
  * The service will be decorated with the standard `@async_timed` decorator for repository calls.

## 7\. Edge Cases & Data Quality

  * **Insufficient Data:** Any metric requiring variance (e.g., Volatility, Sharpe) will return `None` if fewer than two data points are available for a period. The `details` field in the response will contain a reason.
  * **Gaps/NaNs:** The initial return series from `PerformanceCalculator` is already clean. When joining with a benchmark, days with missing data in either series will be dropped (inner join).
  * **Benchmark Alignment:** The service will warn in the logs if the number of aligned data points between the portfolio and benchmark is below a certain threshold (e.g., 80% of the period length).

## 8\. Implementation Plan

The implementation will proceed in small, incremental steps:

1.  **Library Skeleton:** Create the `risk-analytics-engine` directory structure with `__init__.py`, `constants.py`, and `exceptions.py`.
2.  **DTOs:** Implement the full `risk_dto.py` file in `query-service`.
3.  **Router and Service Skeleton:** Create `routers/risk.py` and `services/risk_service.py` with the main endpoint and service class structure, wired into `main.py`.
4.  **Core Logic:** Implement the service logic for data fetching (`PerformanceRepository`) and daily return calculation (via `PerformanceCalculator`).
5.  **Engine Metric \#1 (Volatility):** Implement the volatility calculation in `risk-analytics-engine` and integrate it into the service. Add unit tests.
6.  **Engine Metric \#2 (Drawdown):** Implement and integrate drawdown. Add unit tests.
7.  **(Continue for each metric):** Sequentially implement Sharpe, Sortino, Beta, Tracking Error, Information Ratio, and finally VaR, with unit tests and service integration for each.
8.  **Integration Tests:** Add integration tests for the `/risk` endpoint in `tests/integration/query_service`.
9.  **README Update:** Update `README.md` to document the new API endpoint.