# Feature Documentation: Performance Analytics

## 1. Summary

The Performance Analytics feature provides on-the-fly calculation of industry-standard portfolio performance metrics. It is exposed via the `query_service` and is designed to be highly flexible and consistent with all other analytics in the system.

The service offers two distinct types of performance measurement:

* **Time-Weighted Return (TWR):** Measures the compound rate of growth in a portfolio by removing the distorting effects of external cash flows. This is the industry standard for judging a portfolio manager's performance.
* **Money-Weighted Return (MWR):** Measures the portfolio's internal rate of return (IRR), which *is* influenced by the timing and size of cash flows. This is the standard for understanding the performance from the client's perspective.

All calculations are performed dynamically using the pre-aggregated `portfolio_timeseries` data, ensuring that performance figures are always up-to-date and perfectly consistent with the data used by the Risk Analytics engine.

## 2. Key Features

* **On-the-Fly Calculation:** No performance data is pre-calculated or stored. Results are computed at request time for maximum data freshness.
* **Flexible Period Definition:** The API supports a wide range of period types, including standard relative periods (YTD, MTD, QTD, etc.), calendar years, and explicit start/end dates.
* **Net/Gross Returns:** TWR can be calculated on a NET (after fees) or GROSS (before fees) basis.
* **Detailed Breakdowns:** TWR results can be broken down into daily, weekly, monthly, or quarterly sub-periods.
* **Dual-Currency Support:** All calculations can be performed in the portfolio's base currency, correctly accounting for FX fluctuations.

## 3. Gaps and Design Considerations

* **Engine Maintainability:** The core `performance-calculator-engine` for TWR contains complex, stateful, iterative logic that is difficult to read and maintain. While functionally correct, a refactor to use modern, vectorized pandas operations would significantly improve clarity, reduce complexity, and likely increase performance.
* **Missing Metrics:** The endpoints lack specific Prometheus metrics to distinguish between TWR and MWR calculation latency or to track the usage of different period types. This makes it difficult to monitor the performance and usage of this feature in detail.