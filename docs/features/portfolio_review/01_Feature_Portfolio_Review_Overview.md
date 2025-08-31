# Feature Documentation: Portfolio Review API

## 1. Summary

This document provides a comprehensive overview of the Portfolio Review feature, available through a single, powerful endpoint in the `query-service`. This feature is designed to be the primary data source for client-facing reports, providing a holistic, multi-section view of a portfolio's state from a single, efficient API call.

It acts as a server-side orchestrator, combining data from multiple underlying analytical services to generate a consolidated report. This ensures that all data presented is consistent, reliable, and calculated from the same atomic snapshot of the portfolio's history.

## 2. Key Features

The service generates a report containing the following sections, each drawing from a pre-configured, standardized set of analytics:

* **Overview**: A high-level summary including total wealth, cash balance, the portfolio's assigned risk profile, and a Year-to-Date (YTD) Profit & Loss summary.
* **Asset Allocation**: A comprehensive breakdown of the portfolio's holdings across all available dimensions, including by asset class, sector, currency, and country of risk.
* **Performance**: A standardized view of the portfolio's Time-Weighted Return (TWR) across key periods (MTD, QTD, YTD, 1-Year, 3-Year, Since Inception) on both a NET and GROSS basis.
* **Risk Analytics**: A summary of key risk metrics (Volatility, Sharpe Ratio) for YTD and 3-Year periods.
* **Income & Activity**: A YTD summary of all income (dividends, interest) and external cash flow activity (deposits, withdrawals, fees).
* **Holdings**: A detailed list of all current positions, conveniently grouped by asset class.
* **Transactions**: A list of all transactions that have occurred within the YTD period, grouped by asset class.

## 3. Core Concepts

### 3.1. Server-Side Orchestration

To guarantee data consistency and simplify client applications, all data aggregation is performed on the backend within a single API request. The `ReviewService` makes parallel, in-process calls to the other analytical services (`SummaryService`, `PerformanceService`, etc.) to gather the necessary data.

### 3.2. Atomic Data Consistency (Epoch-Awareness)

This is the most critical design principle of the feature. All underlying data queries are fundamentally **epoch-aware**. The service joins with the `position_state` table for every data fetch to ensure that it only aggregates data belonging to the **current, active `epoch`** for each security. This provides an atomic, consistent snapshot of the portfolio and prevents any data from stale or in-progress reprocessing flows from corrupting the report.

### 3.3. Simple, Standardized Contract

The API is intentionally designed for simplicity. The client requests the sections it needs, and the server returns a rich, pre-configured payload. The business logic for what defines a "standard review" (e.g., which time periods or risk metrics to show) is owned and managed by the backend, ensuring a consistent experience across all client applications.