# Feature Documentation: Position-Level Analytics

## 1. Summary

The Position-Level Analytics feature provides a powerful, consolidated, on-the-fly analytical view of each individual position within a portfolio. It is exposed via a single, highly configurable endpoint in the `query_service`: `POST /portfolios/{portfolio_id}/positions-analytics`.

This service is designed to be the primary data source for any user interface that displays a portfolio's holdings. It goes beyond simply listing positions by enriching each holding with a configurable set of key metrics, including **performance (TWR), total income, held-since date, and portfolio weight**.

## 2. Key Features

* **On-the-Fly Enrichment:** All analytical data is calculated at request time, ensuring the results are always based on the latest, fully processed data available in the system.
* **Comprehensive Data:** A single API call can retrieve a position's quantity, cost basis, market value, unrealized P&L, instrument reference data, income, and performance history.
* **Full Dual-Currency Support:** All monetary values (market value, income, etc.) and performance returns are calculated and returned in both the instrument's local currency and the portfolio's base currency.
* **Configurable Payloads:** Clients can request only the specific analytical "sections" they need, minimizing payload size and calculation time.
* **Epoch-Aware Consistency:** All underlying data queries are strictly filtered by the current, active `epoch` for each security. This guarantees that the analytics for each position are atomically consistent with all other portfolio-level reports.

## 3. Gaps and Design Considerations

* **Scalability and Performance:** The on-the-fly calculation of Time-Weighted Return (TWR) for **every single position** in a portfolio can be computationally expensive and lead to high API latency, especially for portfolios with hundreds or thousands of holdings over long time periods. The current implementation accepts this trade-off for data freshness, but a future enhancement could involve caching or selective pre-calculation for common periods to improve performance.