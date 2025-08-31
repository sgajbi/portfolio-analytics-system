# Feature Documentation: On-the-Fly Concentration Analytics

## 1. Summary

This document provides a comprehensive overview of the Concentration Analytics feature, available through a new, powerful endpoint in the `query-service`. This feature allows clients to compute critical portfolio risk metrics that are not captured by standard deviation, focusing on the risks of over-reliance on single entities or small groups of assets.

The calculations are performed on-demand, ensuring the results are always based on the latest available data for the portfolio's active version (epoch), guaranteeing consistency with all other on-the-fly analytics like risk and performance.

## 2. Key Features

The service provides the following metrics, calculated for a given portfolio and date:

* **Bulk Concentration**: Measures the portfolio's overall level of diversification.
    * **Single-Position Concentration**: The weight of the single largest holding.
    * **Top-N Concentration**: The combined weight of the Top 'N' largest positions (e.g., Top-5, Top-10).
    * **Herfindahl-Hirschman Index (HHI)**: A standard measure of market concentration, where a higher value indicates a less diversified portfolio.
* **Issuer Concentration**: Measures the total exposure to a single corporate entity, rolled up to its ultimate parent.
    * **Fund Look-Through**: For fund holdings (ETFs, Mutual Funds), the engine can optionally "look through" to the underlying constituents to provide a more accurate picture of true issuer exposure.

## 3. Core Concepts

### 3.1. On-the-Fly Calculation

No concentration metrics are pre-calculated or stored in the database. When a request is received, the `query-service` fetches the necessary underlying data (positions and instrument details) for the appropriate epoch and computes the results dynamically. This guarantees data freshness and consistency with all other analytics.

### 3.2. Stateless, Reusable Engine

All financial logic is encapsulated in a new, self-contained `concentration-analytics-engine` shared library. This engine is purely computational (stateless), making it highly deterministic, portable, and easy to unit test in isolation.

### 3.3. Data Consistency (Epoch-Awareness)

All underlying data queries are fundamentally **epoch-aware**. The service joins with the `position_state` table to ensure that it only aggregates data belonging to the current, active `epoch` for each security. This is critical for data integrity, as it prevents stale data from a previous, incomplete reprocessing flow from being included in the calculations.

## 4. How to Use

The feature is exposed via a single, consolidated API endpoint in the `query-service`. Clients send a `POST` request specifying the portfolio, date, and desired metrics.

* **Endpoint**: `POST /portfolios/{portfolio_id}/concentration`
* **Detailed Specification**: See [02_API_Specification_Concentration_Analytics.md](./02_API_Specification_Concentration_Analytics.md)