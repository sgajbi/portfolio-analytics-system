# ADR-001: On-the-Fly Risk Analytics Service Design

* **Status**: Decided
* **Date**: 2025-08-29

## Context

The system required a new capability to provide users with standard portfolio risk metrics (Volatility, Sharpe, VaR, etc.). The key requirements were that these metrics needed to be configurable, consistent with existing performance (TWR) figures, and exposed via the existing `query-service` without adding new persistent storage.

## Decision

We decided on a three-part architecture:
1.  **On-the-Fly Calculation**: All risk metrics are calculated on-demand at request time. There is no new persistence layer for the results. The calculation is performed within the `query-service`.
2.  **Reuse of Performance Engine**: The service reuses the existing `performance-calculator-engine` to generate the foundational daily return series. This series is then passed to a new, dedicated `risk-analytics-engine` for the final metric calculations.
3.  **Single Multi-Metric API Endpoint**: For v1, we implemented a single `POST /portfolios/{portfolio_id}/risk` endpoint that can calculate multiple metrics for multiple periods in one call, instead of creating separate endpoints for each metric (e.g., `/risk/volatility`).

## Consequences

### 1. On-the-Fly Calculation

* **Pros**:
    * **Data Freshness**: Metrics always reflect the absolute latest time-series data without any caching or batching delays.
    * **Reduced Complexity**: Avoids the need for new database tables, storage management, and cache invalidation logic.
    * **Flexibility**: Users can request any combination of periods and parameters without being limited to pre-computed results.
* **Cons**:
    * **Higher Read Latency**: API response times are directly tied to the complexity of the request (number of periods, length of date ranges). This is a trade-off for freshness.
    * **Repetitive Computation**: The system may re-calculate the exact same result if clients make identical requests repeatedly. This can be mitigated with an API gateway cache in the future if it becomes a performance issue.

### 2. Reuse of Performance Engine

* **Pros**:
    * **Consistency Guaranteed**: By using the same daily return calculation as the TWR endpoint, we ensure that risk and return figures are always derived from the same underlying data and logic. This is the most significant benefit.
    * **DRY Principle**: Avoids duplicating complex return calculation logic (handling of fees, cashflows, etc.).
* **Cons**:
    * **Tight Coupling**: The Risk Analytics feature is now tightly coupled to the `performance-calculator-engine`. Any changes or bugs in the performance engine will directly impact risk calculations. This is an accepted trade-off for the benefit of consistency.

### 3. Single Multi-Metric API Endpoint

* **Pros**:
    * **Client Efficiency**: A UI or client system can fetch all necessary risk metrics for a report in a single network call, which is highly efficient.
    * **Backend Efficiency**: The service can fetch the underlying time-series data once and reuse it for all requested metric calculations.
    * **Simplified Implementation**: Reduces the number of routes to maintain and eliminates code duplication in the router and service layers.
* **Cons**:
    * **Complex Request Body**: The JSON request body is more complex than a simple `GET` request with query parameters. This is a minor trade-off for the flexibility it provides.