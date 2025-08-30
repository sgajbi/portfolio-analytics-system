# Feature Documentation: Portfolio Summary API

## 1. Summary

This document provides a comprehensive overview of the Portfolio Summary feature, available through a single, powerful endpoint in the `query-service`. This feature allows clients to retrieve a consolidated, dashboard-style view of a portfolio's state as of a given date.

It is designed to be highly efficient for front-end applications, allowing a complete dashboard to be populated with a single API call. The calculations are performed on-the-fly, ensuring the data always reflects the latest state of the portfolio's active data version (epoch).

## 2. Key Features

The service provides the following summary sections, all calculated for a user-defined period (e.g., YTD, MTD, custom range):

* **Wealth Summary**: The total market value of all holdings (including cash) and the total cash balance.
* **P&L Summary**: A breakdown of the portfolio's change in value, including:
    * Net New Money (contributions - withdrawals)
    * Realized Profit & Loss from sales
    * Change in Unrealized Profit & Loss
    * Total Profit & Loss
* **Income & Activity Summaries**: Aggregated totals for key cashflow events like dividends, interest, fees, deposits, and withdrawals.
* **Multi-Dimensional Asset Allocation**: A breakdown of portfolio holdings by various dimensions, made possible by the enrichment of the `Instrument` data model. Supported dimensions include:
    * Asset Class
    * Sector
    * Currency
    * Country of Risk
    * Credit Rating
    * Maturity Bucket

## 3. Core Concepts

### 3.1. On-the-Fly Calculation

Similar to the Risk and Performance APIs, no summary data is pre-calculated or stored. When a request is received, the `query-service` fetches all the necessary underlying data (positions, transactions, cashflows) for the appropriate epoch and computes the results dynamically. This guarantees data freshness and consistency.

### 3.2. Epoch-Awareness

All underlying queries are fundamentally **epoch-aware**. The service joins with the `position_state` table to ensure that it only aggregates data belonging to the current, active `epoch` for each security. This is critical for data integrity, as it prevents stale data from a previous, incomplete reprocessing flow from being included in the summary.

### 3.3. Single, Consolidated Endpoint

To maximize efficiency for clients, the feature is exposed via a single `POST /portfolios/{portfolio_id}/summary` endpoint. Using `POST` allows for a rich, complex request body where the client can specify exactly which sections and allocation dimensions they require, avoiding the overhead of multiple separate API calls.