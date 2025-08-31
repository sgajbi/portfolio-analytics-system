### RFC 017: Position-Level Analytics API

  * **Status**: Final
  * **Date**: 2025-08-31
  * **Services Affected**: `query-service`, `portfolio-common`
  * **Related RFCs**: RFC 007, RFC 008, RFC 012

-----

## 1\. Summary (TL;DR)

This RFC proposes the creation of a new, configurable endpoint, **`POST /portfolios/{portfolio_id}/positions-analytics`**, within the `query-service`. This endpoint will provide a comprehensive, on-the-fly analytical view of each individual position within a portfolio.

The new feature will enrich each position with key metrics, including **performance (TWR), total income, held since date, and portfolio weight**, along with a full set of instrument reference data. All analytics will be calculated in both the instrument's local currency and the portfolio's base currency. The design reuses the existing `performance-calculator-engine`, adheres to the system's **epoch-aware** data consistency model, and follows the established architectural pattern of stateless, on-demand calculations.

-----

## 2\. Motivation

While the system provides excellent portfolio-level analytics, advisors and clients require deeper insights into the individual drivers of performance and risk. Manually calculating these metrics is time-consuming and error-prone. This feature will empower users by:

  * **Providing Actionable Insights**: Quickly identify top/bottom performers, significant income generators, and long-term holdings.
  * **Enhancing Client Conversations**: Answer specific client questions like, "How has this particular stock performed since we bought it?" with precise, data-driven answers.
  * **Improving Efficiency**: Aggregate all necessary position-level data into a single, configurable API call, streamlining front-end development and reducing network overhead.

-----

## 3\. Proposed Architecture & Design

The implementation will be logically contained within the `query-service` and will follow patterns established by the existing on-the-fly analytics endpoints (`/risk`, `/summary`).

### 3.1. New API Endpoint

A new endpoint will be created: **`POST /portfolios/{portfolio_id}/positions-analytics`**.

We will use the `POST` method to accommodate a rich, JSON-based request body. This provides maximum flexibility for clients to request only the specific analytical sections they need, which is more scalable than using a large number of query parameters.

### 3.2. New `PositionAnalyticsService`

A new `PositionAnalyticsService` will be created within `src/services/query_service/app/services/`. This service will act as the primary orchestrator for this feature. Its responsibilities will be to:

1.  Parse the incoming `PositionAnalyticsRequest`.
2.  Fetch the base position data for the portfolio using the `PositionRepository`.
3.  For each position, concurrently execute the required analytical enrichment tasks (e.g., performance calculation, income summation) using `asyncio.gather`, mirroring the efficient orchestration pattern used in the `ReviewService`.
4.  Assemble the final, enriched `PositionAnalyticsResponse`.

### 3.3. Data Consistency (Epoch-Awareness)

This feature's reliability hinges on adhering to the system's epoch/watermark model. All underlying repository methods used by the `PositionAnalyticsService` **must** be epoch-aware. Every query for historical or stateful data (from `daily_position_snapshots`, `position_history`, `position_timeseries`, etc.) will join with the `position_state` table and filter on `table.epoch = position_state.epoch` for the given key. This guarantees that all calculations are performed on an atomically consistent and complete version of the data, preventing corruption from in-progress reprocessing flows.

-----

## 4\. Detailed Calculation Methodologies

| Metric | Primary Data Source(s) | Calculation Strategy |
| :--- | :--- | :--- |
| **Base Position Data** | `daily_position_snapshots` | Use the existing `PositionRepository.get_latest_positions_by_portfolio` method. This provides the core data: quantity, market value (local and base), and cost basis (local and base) for each open position as of the request date. |
| **Instrument Enrichment** | `instruments` | The `PositionRepository` method will be extended to join and retrieve all relevant fields from the `instruments` table, including `name`, `isin`, `asset_class`, `sector`, `country_of_risk`, and `currency`. |
| **`held_since_date`** | `position_history` | This date will be derived dynamically by a new method in `PositionRepository`. The logic will find the most recent date where the position quantity was zero (or non-existent) for the current epoch; the `held_since_date` is the `transaction_date` of the first record *after* that point. If no such point exists, the date of the very first `position_history` record for the current epoch is used. |
| **`total_income`** | `cashflows`, `fx_rates` | A new repository method will sum all records from the `cashflows` table where `security_id` matches the position and `classification` is `INCOME` since the `held_since_date`. This will be done twice: once summing the `amount` for the local currency total, and a second time converting each `amount` to the portfolio's base currency using the historical `fx_rates` for each `cashflow_date`. |
| **`weight`** | `daily_position_snapshots` | Calculated as `position.market_value_base / portfolio_total_market_value_base`. The portfolio's total market value is the sum of `market_value_base` across all positions fetched in the initial step. |
| **Performance (TWR)** | `position_timeseries`, `fx_rates` | We will create a new internal component to reuse the `performance-calculator-engine`. For each position and requested period (MTD, YTD, etc.): \<br\> 1. Fetch the corresponding data from the `position_timeseries` table, which is at the correct granularity. \<br\> 2. Instantiate `PerformanceCalculator` and calculate the return. This yields the performance in the **local currency**. \<br\> 3. To get the **base currency** return, fetch the daily FX rates for the period, apply them to the daily return series, and recalculate. This correctly captures the P\&L contribution from both asset price movement and currency fluctuations. |

-----

## 5\. API Schema Definition

A new DTO file will be created: `src/services/query_service/app/dtos/position_analytics_dto.py`.

#### **Request: `POST /portfolios/{portfolio_id}/positions-analytics`**

```json
{
  "as_of_date": "2025-08-31",
  "sections": [
    "BASE",
    "INSTRUMENT_DETAILS",
    "INCOME",
    "PERFORMANCE"
  ],
  "performance_options": {
    "periods": ["MTD", "YTD", "ONE_YEAR", "SI"]
  }
}
```

#### **Response Body**

```json
{
  "portfolio_id": "E2E_REVIEW_01",
  "as_of_date": "2025-08-31",
  "total_market_value": 101270.00,
  "positions": [
    {
      "security_id": "SEC_AAPL",
      "quantity": 100.0,
      "market_value": 16000.00,
      "weight": 0.158,
      "held_since_date": "2025-08-20",
      
      "instrument_details": {
        "name": "Apple Inc.",
        "isin": "US_AAPL_REVIEW",
        "asset_class": "Equity",
        "sector": "Technology",
        "country_of_risk": "US",
        "currency": "USD"
      },

      "income": {
        "local": {
          "currency": "USD",
          "amount": 120.00
        },
        "base": {
          "currency": "USD",
          "amount": 120.00
        }
      },

      "performance": {
        "MTD": {
          "local_return": 5.25,
          "base_return": 5.25
        },
        "YTD": {
          "local_return": 12.80,
          "base_return": 12.80
        }
      }
    }
  ]
}
```

-----

## 6\. Observability

To monitor this new, high-value endpoint, the following will be implemented:

  * **Metrics**:
      * `position_analytics_duration_seconds` (`Histogram`): Measures the end-to-end latency of a full API request, labeled by `portfolio_id`.
      * `position_analytics_section_requested_total` (`Counter`): Tracks how often each section (`PERFORMANCE`, `INCOME`, etc.) is requested to monitor feature usage.
  * **Logging**: The `PositionAnalyticsService` will emit structured logs tagged with `correlation_id`, `portfolio_id`, and the number of positions processed to provide a clear trace of each request.

-----

## 7\. Implementation Plan

1.  **Phase 1: Foundation (DTOs, Service & Repository Layers)**:
      * Create all DTOs for the request and response.
      * Create the `PositionAnalyticsService` skeleton and the `POST /positions-analytics` router in `query_service`.
      * Enhance `PositionRepository` to fetch the required base position and instrument data in a single, optimized query.
2.  **Phase 2: Core Analytics (Income & Held Since Date)**:
      * Implement the repository method and service logic to derive the `held_since_date`.
      * Implement the repository method and service logic for the dual-currency `total_income` calculation.
3.  **Phase 3: Performance Calculation**:
      * Create a new repository method to fetch data from the `position_timeseries` table.
      * Implement the service logic to call the `performance-calculator-engine` for both local and base currency returns.
4.  **Phase 4: Testing & Observability**:
      * Add the Prometheus metrics and structured logging.
      * Add comprehensive unit tests for all new logic, integration tests for the endpoint, and a new end-to-end test to validate the entire pipeline.

-----

## 8\. Risks & Mitigations

  * **Performance Risk**: Calculating performance for every position in a large portfolio could be slow.
      * **Mitigation**: The use of `asyncio.gather` will parallelize the work. All database queries will be optimized and analyzed. If performance issues arise for very large portfolios, we can consider adding a caching layer in a future iteration.
  * **Data Dependency Risk**: The accuracy of the analytics is highly dependent on the completeness of the upstream `position_timeseries` data.
      * **Mitigation**: The API will fail gracefully. If the time-series data required for a calculation is missing, the corresponding section in the response (e.g., `performance`) will be `null`. This provides a clear signal of upstream data lag without failing the entire request.

-----

## 9\. Acceptance Criteria

1.  The new `POST /portfolios/{portfolio_id}/positions-analytics` endpoint is implemented and functional.
2.  The API response is configurable via the `sections` array in the request body.
3.  All calculations are verifiably epoch-aware.
4.  Performance and income are correctly calculated and returned in both local and portfolio base currencies.
5.  The `performance-calculator-engine` is reused for position-level TWR calculations.
6.  The new feature is covered by unit, integration, and end-to-end tests.
7.  New Prometheus metrics for latency and feature usage are implemented.