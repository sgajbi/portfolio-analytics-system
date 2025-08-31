### RFC 017: Position-Level Analytics API

  * **Status**: Final
  * **Date**: 2025-08-31
  * **Services Affected**: `query-service`, `portfolio-common`
  * **Related RFCs**: RFC 007, RFC 008, RFC 012

-----

## 1\. Summary (TL;DR)

This RFC approves the creation of a new, configurable endpoint, **`POST /portfolios/{portfolio_id}/positions-analytics`**, within the `query-service`. This endpoint will provide a comprehensive, on-the-fly analytical view of each individual position within a portfolio.

The new feature will enrich each position with key metrics, including **performance (TWR), total income, held since date, and portfolio weight**, along with a full set of instrument reference data. All analytics will be calculated in both the instrument's local currency and the portfolio's base currency. The design reuses the existing `performance-calculator-engine`, adheres to the system's **epoch-aware** data consistency model, and follows the established architectural pattern of stateless, on-demand calculations.

-----

## 2\. Motivation

While the system provides excellent portfolio-level analytics, advisors and clients need deeper insights into the individual drivers of performance and risk. Manually calculating these metrics is time-consuming and error-prone. This feature will empower users by:

  * **Providing Actionable Insights**: Quickly identify top/bottom performers, significant income generators, and long-term holdings.
  * **Enhancing Client Conversations**: Answer specific client questions like, "How has this particular stock performed since we bought it?" with precise, data-driven answers.
  * **Improving Efficiency**: Aggregate all necessary position-level data into a single, configurable API call, streamlining front-end development and reducing network overhead.

-----

## 3\. Proposed Architecture & Design

The implementation will be logically contained within the `query-service` and will follow patterns established by the existing on-the-fly analytics endpoints (`/risk`, `/summary`).

### 3.1. New API Endpoint

A new endpoint will be created: **`POST /portfolios/{portfolio_id}/positions-analytics`**.

We will use the `POST` method to allow for a rich, JSON-based request body. This provides maximum flexibility for clients to request only the specific analytical sections they need, which is more scalable than using a large number of query parameters.

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
| **Base Position & Valuation** | `daily_position_snapshots`, `instruments` | We will extend the existing `PositionRepository.get_latest_positions_by_portfolio` method to fetch all required instrument reference data in a single, efficient query. This provides the core data: quantity, market value (local and base), and cost basis (local and base). Unrealized P\&L is derived from these values. |
| **`held_since_date`** | `position_history` | This date will be derived dynamically. We will query for the most recent date *before* the current holding period where the position quantity was zero. The `held_since_date` will be the date of the subsequent transaction that re-opened the position. If no such zero-quantity point exists, the date of the very first transaction will be used. |
| **`total_income`** | `cashflows`, `fx_rates` | We will sum all records from the `cashflows` table where the `classification` is `INCOME` for the specific position since its `held_since_date`. The calculation will first be performed in the instrument's local currency. A second calculation will convert each cashflow amount to the portfolio's base currency using the FX rate from the respective `cashflow_date`. |
| **`weight`** | `daily_position_snapshots` | Calculated as `position.market_value_base / portfolio_total_market_value_base`. The portfolio's total market value is the sum of `market_value_base` across all positions fetched in the initial step. |
| **Performance (TWR)** | `position_timeseries`, `fx_rates` | We will reuse the `performance-calculator-engine`. For each position and requested period: \<br\> 1. Fetch the corresponding data from the `position_timeseries` table. \<br\> 2. Instantiate `PerformanceCalculator` and calculate the return. This yields the performance in the **local currency**. \<br\> 3. To get the **base currency** return, we will fetch the daily FX rates for the period, apply them to the daily return series, and run the calculation a second time. This correctly captures the P\&L contribution from FX movements. |

-----

## 5\. API Schema Definition

A new DTO file will be created: `src/services/query_service/app/dtos/position_analytics_dto.py`. Pydantic models will use `camelCase` aliases to ensure the JSON payload adheres to web API best practices.

#### **Request: `POST /portfolios/{portfolio_id}/positions-analytics`**

```json
{
  "asOfDate": "2025-08-31",
  "sections": [
    "BASE",
    "INSTRUMENT_DETAILS",
    "VALUATION",
    "INCOME",
    "PERFORMANCE"
  ],
  "performanceOptions": {
    "periods": ["MTD", "QTD", "YTD", "ONE_YEAR", "SI"]
  }
}
```

#### **Response Body**

```json
{
  "portfolioId": "E2E_REVIEW_01",
  "asOfDate": "2025-08-31",
  "totalMarketValue": 101270.00,
  "positions": [
    {
      "securityId": "SEC_AAPL",
      "quantity": 100.0,
      "weight": 0.158,
      "heldSinceDate": "2025-08-20",
      
      "instrumentDetails": {
        "name": "Apple Inc.",
        "isin": "US_AAPL_REVIEW",
        "assetClass": "Equity",
        "sector": "Technology",
        "countryOfRisk": "US",
        "currency": "USD"
      },

      "valuation": {
        "marketValue": {
          "local": {"amount": 16000.00, "currency": "USD"},
          "base": {"amount": 16000.00, "currency": "USD"}
        },
        "costBasis": {
          "local": {"amount": 15000.00, "currency": "USD"},
          "base": {"amount": 15000.00, "currency": "USD"}
        },
        "unrealizedPnl": {
          "local": {"amount": 1000.00, "currency": "USD"},
          "base": {"amount": 1000.00, "currency": "USD"}
        }
      },

      "income": {
        "local": {"amount": 120.00, "currency": "USD"},
        "base": {"amount": 120.00, "currency": "USD"}
      },

      "performance": {
        "YTD": {
          "localReturn": 12.80,
          "baseReturn": 12.80
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
      * `position_analytics_duration_seconds` (`Histogram`): Measures the end-to-end latency of a full API request.
      * `position_analytics_section_requested_total` (`Counter`): Tracks how often each section (`PERFORMANCE`, `INCOME`) is requested to monitor feature usage.
  * **Logging**: The `PositionAnalyticsService` will emit structured logs tagged with `correlation_id`, `portfolio_id`, and the number of positions processed to provide a clear trace of each request.

-----

## 7\. Acceptance Criteria

1.  A new `POST /portfolios/{portfolio_id}/positions-analytics` endpoint exists in the `query_service`.
2.  The API response is configurable via the `sections` array in the request body.
3.  All calculations are verifiably epoch-aware and consistent with other system analytics.
4.  All monetary values (market value, cost basis, P\&L, income) and performance returns are correctly calculated and returned in both local and portfolio base currencies.
5.  The `performance-calculator-engine` is reused for position-level TWR calculations.
6.  The new feature is covered by comprehensive unit, integration, and end-to-end tests.
7.  New Prometheus metrics for latency and feature usage are implemented.