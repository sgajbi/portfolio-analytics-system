# Feature Documentation: On-the-Fly Risk Analytics

## 1. Summary

This document provides a comprehensive overview of the Risk Analytics feature available through the `query-service`. This feature allows clients to compute a suite of industry-standard, portfolio-level risk metrics dynamically.

The core design principle is **consistency**: all risk metrics are derived from the same daily time-series data and daily return calculations used by the Time-Weighted Return (TWR) performance endpoint. This guarantees that risk and return figures are always calculated on the same basis.

## 2. Key Features

The service provides the following metrics, calculated on-demand for any specified period:

* **Volatility**: Annualized standard deviation of returns.
* **Sharpe Ratio**: Risk-adjusted return, measured against a configurable risk-free rate.
* **Sortino Ratio**: A variation of the Sharpe Ratio that only penalizes for downside volatility below a Minimum Acceptable Return (MAR).
* **Drawdown**: The maximum peak-to-trough decline of the portfolio's value during a period, including peak and trough dates.
* **Benchmark-Relative Metrics**:
    * **Beta ($\beta$)**: Measures the portfolio's volatility relative to a specified benchmark.
    * **Tracking Error**: Measures the standard deviation of the difference between the portfolio's and the benchmark's returns.
    * **Information Ratio**: Measures a portfolio's risk-adjusted active return.
* **Value at Risk (VaR)**: Estimates the potential loss over a given time horizon at a specific confidence level, available using three methods:
    * **Historical**: Based on the empirical distribution of past returns.
    * **Gaussian (Parametric)**: Based on a normal distribution assumption.
    * **Cornish-Fisher**: An adjusted parametric method that accounts for skewness and kurtosis in returns.
* **Expected Shortfall (ES / CVaR)**: Calculates the average loss expected in the tail of the distribution beyond the VaR threshold (optional).

## 3. Core Concepts

### 3.1. On-the-Fly Calculation

No risk metrics are pre-calculated or stored in the database. When a request is received, the `query-service`:
1.  Fetches the raw, daily `portfolio_timeseries` data for the portfolio's current, active epoch.
2.  Instantiates the `performance-calculator-engine` to generate a daily return series.
3.  Passes this return series to the `risk-analytics-engine` to compute the requested metrics.

This ensures that the metrics always reflect the latest available data and that there is no data staleness.

### 3.2. Configurability

Nearly every aspect of the calculation is configurable via the API request body, including:
* **Periods**: Any number of periods (YTD, MTD, explicit date ranges, etc.).
* **Frequency**: Calculations can be based on `DAILY`, `WEEKLY`, or `MONTHLY` returns.
* **Parameters**: Annualization factors, risk-free rates, benchmark security IDs, and VaR confidence/method can all be specified per-request.

## 4. How to Use

The feature is exposed via a single, powerful API endpoint in the `query-service`. Clients send a `POST` request specifying the portfolio, periods, and desired metrics.

* **Endpoint**: `POST /portfolios/{portfolio_id}/risk`
* **Detailed Specification**: See [02_API_Specification_Risk_Analytics.md](./02_API_Specification_Risk_Analytics.md) (To be created in the next step).

This concludes the high-level overview. The subsequent documents in this directory will provide detailed API specifications and methodology guides.