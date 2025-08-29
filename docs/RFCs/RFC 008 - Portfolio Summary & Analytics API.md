# RFC 008: Portfolio Summary & Analytics API

* **Status**: Proposed
* **Date**: 2025-08-29
* **Services Affected**: `query-service`, `ingestion_service`, `persistence_service`, `portfolio-common`

---

## 1. Summary (TL;DR)

This RFC proposes the creation of a new, consolidated `POST /portfolios/{portfolio_id}/summary` endpoint in the `query-service`. This endpoint will provide a holistic, dashboard-style view of a portfolio's state as of a given date, designed to be highly efficient for front-end applications.

The summary will include:
* **Total Wealth & Total Cash**
* **Contribution & P&L Summary** (Net New Money, Realized/Unrealized P&L)
* **Income & Activity Summaries** (Dividends, Interest, Fees, etc.)
* **Asset Allocation**

A core prerequisite for the Asset Allocation feature is the enrichment of the `Instrument` data model. This RFC includes a plan to add several new **optional** fields (`assetClass`, `sector`, `country_of_risk`, etc.) to the `instruments` table, along with the necessary updates to the ingestion and persistence pipelines.

## 2. Motivation

Client advisors and portfolio managers require a single, at-a-glance dashboard view to quickly assess a portfolio's overall status. Currently, retrieving this information would require multiple, separate API calls to different endpoints, which is inefficient for both the client and the backend.

By creating a single, powerful `/summary` endpoint, we can:
* **Improve Client Efficiency**: Allow a UI to fetch all necessary data for a dashboard in a single network request.
* **Optimize Backend Performance**: Design the service to fetch underlying data from the database once and compute all summary metrics from that single dataset.
* **Enhance Analytical Capabilities**: The enrichment of the `Instrument` model is a foundational improvement that unlocks sophisticated, multi-dimensional asset allocation analysis, a critical feature for any portfolio management system.

## 3. Proposed Changes

### 3.1. Prerequisite: Instrument Model Enrichment

To enable multi-dimensional asset allocation, the `instruments` table schema must be updated. All new fields will be **optional (`nullable=True`)** to ensure full backward compatibility with existing data and ingestion flows.

**New Fields for `instruments` Table:**

| New Field         | Data Type | Description                                                                |
| ----------------- | --------- | -------------------------------------------------------------------------- |
| `assetClass`      | `VARCHAR` | High-level, standardized category (e.g., 'Equity', 'Fixed Income', 'Cash'). |
| `sector`          | `VARCHAR` | Industry sector for equities (e.g., 'Technology', 'Healthcare').             |
| `country_of_risk` | `VARCHAR` | The country associated with the instrument's primary risk exposure.          |
| `rating`          | `VARCHAR` | Credit rating for fixed income instruments (e.g., 'AAA', 'BB+').             |
| `maturity_date`   | `DATE`    | Maturity date for fixed income instruments.                                |

This change will require:
1.  An **Alembic migration** to alter the table.
2.  Updates to the `InstrumentEvent` in `portfolio-common` and the `Instrument` DTO in `ingestion_service` to accept these new optional fields.
3.  Updates to the `InstrumentConsumer` in `persistence_service` to save the new fields to the database.

### 3.2. New API Endpoint: `POST /portfolios/{portfolio_id}/summary`

A single endpoint will accept a request specifying the desired summary sections and calculation parameters.

**Request Body (`SummaryRequest`):**

```json
{
  "as_of_date": "2025-08-29",
  "period": {
    "type": "YTD"
  },
  "sections": [
    "WEALTH",
    "ALLOCATION",
    "PNL",
    "INCOME",
    "ACTIVITY"
  ],
  "allocation_dimensions": [
    "ASSET_CLASS",
    "CURRENCY",
    "SECTOR",
    "COUNTRY_OF_RISK",
    "MATURITY_BUCKET"
  ]
}
````

**Response Body (`SummaryResponse`):**

The response will be a JSON object where each requested section is a key.

```json
{
  "scope": {
    "portfolio_id": "...",
    "as_of_date": "...",
    "period_start_date": "...",
    "period_end_date": "..."
  },
  "wealth": {
    "total_market_value": 1250000.50,
    "total_cash": 50000.25
  },
  "pnl_summary": {
    "net_new_money": 10000.00,
    "realized_pnl": 5230.10,
    "unrealized_pnl": 12345.67
  },
  "income_summary": {
    "total_dividends": 850.00,
    "total_interest": 120.50
  },
  "activity_summary": {
    "total_inflows": 15000.00,
    "total_outflows": -5000.00,
    "total_fees": -75.50
  },
  "allocation": {
    "by_asset_class": [
      { "group": "Equity", "market_value": 900000.00, "weight": 0.72 },
      { "group": "Fixed Income", "market_value": 300000.25, "weight": 0.24 },
      { "group": "Unclassified", "market_value": 50000.25, "weight": 0.04 }
    ],
    "by_sector": [
        // ...
    ]
  }
}
```

### 3.3. New Service Logic (`SummaryService`)

A new `SummaryService` in the `query_service` will orchestrate all calculations.

  * **Data Fetching**: The service will efficiently fetch data once from the primary source tables (`daily_position_snapshots`, `instruments`, `transactions`, `cashflows`) for the requested `as_of_date` and period.

  * **Wealth & Cash**: Calculated by summing `market_value` from the latest `daily_position_snapshots`. Total Cash will be filtered by `product_type = 'Cash'`.

  * **P\&L, Income, Activity**: Aggregated by querying the `transactions` and `cashflows` tables for the specified period, filtering by `classification` and `is_portfolio_flow` flags as appropriate.

  * **Asset Allocation**: The service will calculate breakdowns by joining the latest `daily_position_snapshots` (for market values) with the enriched `instruments` table (for dimensional data). Any instrument with a `NULL` value for a requested dimension will be grouped into an **"Unclassified"** category in the response.

    **Supported Allocation Dimensions:**

| Dimension         | Applies To                      | Data Source / Logic                                                                                             |
| ----------------- | ------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| `ASSET_CLASS`     | All                             | Sourced directly from the new `instrument.assetClass` field.                                                    |
| `CURRENCY`        | All                             | Sourced directly from the existing `instrument.currency` field.                                                 |
| `COUNTRY_OF_RISK` | All                             | Sourced directly from the new `instrument.country_of_risk` field.                                               |
| `SECTOR`          | `assetClass='Equity'`           | Sourced directly from the new `instrument.sector` field.                                                        |
| `RATING`          | `assetClass='Fixed Income'`     | Sourced directly from the new `instrument.rating` field.                                                        |
| `MATURITY_BUCKET` | `assetClass='Fixed Income'`     | Calculated on-the-fly: `instrument.maturity_date - as_of_date`. Mapped to buckets (e.g., 0-2Y, 2-5Y, 5-10Y, 10Y+). |

## 4\. High-Level Implementation Plan

1.  **Phase 1: Instrument Model Enrichment (Foundation)**

      * **DB Migration**: Create and apply an Alembic migration to add the new optional fields to the `instruments` table.
      * **DTOs**: Update `InstrumentEvent` (`portfolio-common`) and `Instrument` DTO (`ingestion_service`) to include the new optional fields.
      * **Persistence**: Update `InstrumentConsumer` (`persistence_service`) to handle and persist the new optional fields.
      * **Testing**: Add unit tests to verify the updated ingestion and persistence logic.

2.  **Phase 2: Summary API Implementation (Feature)**

      * **DTOs**: Create all necessary request/response DTOs for the `/summary` endpoint in `query_service`.
      * **Repositories**: Add new query methods to the repositories in `query_service` to efficiently fetch the data needed for all summaries (e.g., aggregating cashflows by classification).
      * **Service**: Implement the new `SummaryService` containing the core business logic for all calculations.
      * **Router**: Create a new `summary.py` router and register the `POST /portfolios/{portfolio_id}/summary` endpoint.
      * **Testing**: Add comprehensive unit and integration tests for the new service and endpoint.

3.  **Phase 3: Documentation & E2E Testing**

      * **E2E Test**: Create a new end-to-end test that ingests an instrument with all new fields and verifies the `/summary` API response.
      * **Documentation**: Update `README.md` to document the new `/summary` API endpoint.

## 5\. Acceptance Criteria

  * The `instruments` table in the database contains the new optional columns (`assetClass`, `sector`, etc.).
  * The `ingestion_service` can successfully receive and publish an instrument payload containing the new fields.
  * The `persistence_service` successfully saves these new fields.
  * A `POST` request to the new `/portfolios/{portfolio_id}/summary` endpoint returns a `200 OK` with a correctly calculated payload for all requested sections.
  * An allocation breakdown requested for a dimension where some instruments have `NULL` values returns an "Unclassified" group.
  * All new logic is covered by unit, integration, and at least one end-to-end test.

 