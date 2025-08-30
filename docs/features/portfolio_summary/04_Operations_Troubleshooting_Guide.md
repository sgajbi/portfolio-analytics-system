# Operations & Troubleshooting Guide: Portfolio Summary

## 1. Summary

This guide provides operational instructions for monitoring, troubleshooting, and supporting the on-the-fly Portfolio Summary feature within the `query-service`.

## 2. Key Dependencies

The Portfolio Summary feature is a read-only process that relies entirely on data already persisted in the main PostgreSQL database. A failure or lack of data in these upstream tables, which are populated by various services, will directly impact the availability and correctness of the summary calculations.

* **`daily_position_snapshots`**: The primary source for all market values and unrealized P&L figures. Populated by the `position-valuation-calculator`.
* **`transactions`**: The source for `realized_pnl`. Populated by the `cost-calculator-service`.
* **`cashflows`**: The source for all `activity` and `income` summaries. Populated by the `cashflow-calculator-service`.
* **`instruments`**: Provides the dimensions for `allocation` breakdowns. Populated by the `persistence_service`.
* **`position_state`**: Crucial for filtering all queries to the correct, active data `epoch`. Populated by the `position-calculator`.

## 3. Observability & Monitoring

The feature exposes key Prometheus metrics via the `query-service`'s `/metrics` endpoint. These should be monitored to understand usage, performance, and data quality.

| Metric Name                                  | Type        | Labels                       | Description & What to Watch For                                                                                                  |
| -------------------------------------------- | ----------- | ---------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| `summary_calculation_duration_seconds`       | `Histogram` | `portfolio_id`               | Measures the latency of a full summary calculation. Spikes could indicate a performance issue with the underlying database queries. |
| `summary_section_requested_total`            | `Counter`   | `section_name`               | Tracks how many times each summary section (e.g., `WEALTH`, `PNL`) has been requested. Helps understand feature usage.      |
| `unclassified_allocation_market_value_total` | `Gauge`     | `portfolio_id`, `dimension`  | **Data Quality KPI.** A high or consistently non-zero value indicates that instrument data is missing for the specified dimension. |

## 4. Structured Logging & Tracing

All logs related to a single API request are tied together with a `correlation_id`. When troubleshooting, always find the `correlation_id` from the `X-Correlation-ID` response header.

**Example Log Flow for a Request:**

1.  **`INFO`**: `Starting summary calculation for portfolio E2E_SUM_PORT_01`
2.  **`INFO`**: `Fetching wealth and allocation data...`
3.  **`INFO`**: `Found 3 open positions for portfolio 'E2E_SUM_PORT_01' for summary as of 2025-08-29.`
4.  **`INFO`**: `Calculating allocation for dimension ASSET_CLASS.`
5.  **`WARN`**: `Unclassified market value for portfolio E2E_SUM_PORT_01 on dimension SECTOR is 754350.00` (Example)
6.  **`INFO`**: `Successfully completed summary calculation for portfolio E2E_SUM_PORT_01`

## 5. Common Failure Scenarios & Resolutions

| Scenario                                     | Symptom(s) in API Response                                      | Key Log Message(s) / Metric Alert                                 | Resolution / Action                                                                                                             |
| -------------------------------------------- | --------------------------------------------------------------- | ----------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| **Portfolio Does Not Exist** | `404 Not Found` with detail `"Portfolio P_FAKE not found"`      | `ValueError: Portfolio P_FAKE not found`                          | Verify the `portfolio_id` with the user. The ID in the URL is incorrect or has not been ingested via the `ingestion_service`.   |
| **High "Unclassified" Allocation** | Allocation breakdowns contain a large "Unclassified" bucket.    | `unclassified_allocation_market_value_total > 0`                  | This indicates a data quality issue. Advise the user/data team to ingest the missing `instrument` data (e.g., `assetClass`, `sector`). |
| **Incorrect P&L or Activity Figures** | User reports that summary numbers do not match expectations.    | (No error logs)                                                   | The issue is likely in upstream data. Trace the calculation back by querying the `transactions` and `cashflows` tables for the period. Escalate to developers if the underlying data appears correct but the summary is still wrong. |
| **Calculation Fails Unexpectedly** | `500 Internal Server Error`                                     | `An unexpected error occurred during summary calculation...`      | **Escalate to the development team.** Provide the full logs, `correlation_id`, and the request body that caused the failure.   |