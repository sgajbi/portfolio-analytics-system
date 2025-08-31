# Methodology Guide: Portfolio Review

This document details the financial methodologies and data sources for each section of the Portfolio Review report. The core principle is that all data is calculated on-the-fly, ensuring it reflects the latest information available for the portfolio's **current, active epoch**.

---

## 1. Data Source Summary

The `/review` endpoint acts as an orchestrator. It does not contain its own financial logic; instead, it delegates calculations to the specialized services within the `query-service`.

| Report Section          | Primary Data Source Service | Key Underlying Tables                                      |
| ----------------------- | --------------------------- | ---------------------------------------------------------- |
| **Overview** | `SummaryService` & `PortfolioService` | `daily_position_snapshots`, `portfolios`, `transactions` |
| **Allocation** | `SummaryService`            | `daily_position_snapshots`, `instruments`                  |
| **Performance** | `PerformanceService`        | `portfolio_timeseries`                                     |
| **Risk Analytics** | `RiskService`               | `portfolio_timeseries`                                     |
| **Income & Activity** | `SummaryService`            | `cashflows`, `transactions`                                |
| **Holdings** | `PositionService`           | `daily_position_snapshots`                                 |
| **Transactions** | `TransactionService`        | `transactions`                                             |

---

## 2. Section-Specific Logic

### 2.1. Overview

* **Total Wealth & Cash**: Sourced from the `SummaryService`. Calculated by summing the `market_value` from the single latest `daily_position_snapshot` for each security held on or before the `as_of_date`.
* **Risk Profile & Portfolio Type**: Sourced directly from the `portfolios` table via the `PortfolioService`.
* **P&L Summary**: Sourced from the `SummaryService`. All P&L figures (`realized_pnl`, `unrealized_pnl_change`) are calculated for a **Year-to-Date (YTD)** period relative to the request's `as_of_date`.

### 2.2. Allocation

* Sourced from the `SummaryService`. The report includes breakdowns for **all available allocation dimensions** as defined in `RFC 008`.
* This includes `by_asset_class`, `by_sector`, `by_currency`, `by_country_of_risk`, `by_rating`, and `by_maturity_bucket`.

### 2.3. Performance

* Sourced from the `PerformanceService`.
* The report contains a static, pre-configured set of periods: **MTD, QTD, YTD, 1-Year, 3-Year, and Since Inception**.
* It includes both cumulative and (where applicable) annualized returns.
* Calculations are provided on both a **NET** and **GROSS** basis.

### 2.4. Risk Analytics

* Sourced from the `RiskService`.
* The report provides a standard set of key risk metrics (e.g., Volatility, Sharpe Ratio) for **YTD** and **3-Year** periods.

### 2.5. Income & Activity

* Sourced from the `SummaryService`.
* Shows a summary of all cashflows for the **YTD period** relative to the `as_of_date`.

### 2.6. Holdings

* Sourced from the `PositionService`.
* Provides a list of all current portfolio holdings as of the `as_of_date`.
* The `ReviewService` performs a final transformation on this list, **grouping the holdings by their `asset_class`** for easier consumption by UIs.

### 2.7. Transactions

* Sourced from the `TransactionService`.
* Provides a list of recent transactions for the **YTD period** relative to the `as_of_date`.
* The `ReviewService` performs a final transformation on this list, **grouping the transactions by their `asset_class`**.

