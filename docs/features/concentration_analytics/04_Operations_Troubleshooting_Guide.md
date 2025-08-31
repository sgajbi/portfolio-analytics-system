# Operations & Troubleshooting Guide: Concentration Analytics

## 1. Summary

This guide provides operational instructions for monitoring and troubleshooting the on-the-fly Concentration Analytics feature, available at `POST /portfolios/{portfolio_id}/concentration`.

## 2. Key Dependencies

The Concentration Analytics feature is a read-only process that relies entirely on data already persisted in the PostgreSQL database. Its health is directly dependent on the correctness and availability of data from these upstream sources:

* **`daily_position_snapshots`**: The primary source for all position market values. Populated by the `position-valuation-calculator`.
* **`instruments`**: Provides the dimensions for issuer concentration (`issuer_id`, `ultimate_parent_issuer_id`). Populated by the `persistence_service`.
* **`position_state`**: Crucial for filtering all queries to the correct, active data `epoch`. Populated by the `position-calculator`.
* **`fx_rates`**: Required for any portfolio that holds instruments in a currency different from its base currency. Populated by the `persistence_service`.

## 3. Observability & Monitoring

The feature exposes key Prometheus metrics via the `query-service`'s `/metrics` endpoint. These should be monitored to understand usage and performance.

| Metric Name                                | Type      | Labels         | Description & What to Watch For                                                                                                     |
| ------------------------------------------ | --------- | -------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `concentration_calculation_duration_seconds` | `Histogram` | `portfolio_id` | **Primary KPI.** Measures the end-to-end latency of a full calculation. Spikes indicate a performance issue in a database query. |
| `concentration_lookthrough_requests_total` | `Counter`   | `portfolio_id` | Tracks how often the fund look-through feature is used. Helps understand usage of the most performance-intensive option.      |

## 4. Structured Logging & Tracing

All logs related to a single API request are tied together with a `correlation_id`. When troubleshooting, always find the `correlation_id` from the `X-Correlation-ID` response header or the logs.

**Example Log Flow for a Request:**

1.  **`INFO`**: `Starting concentration calculation for portfolio E2E_CONC_01`
2.  **`INFO`**: `Fetching latest positions for portfolio E2E_CONC_01...`
3.  **`INFO`**: `Found 3 open positions for portfolio E2E_CONC_01.`
4.  **`INFO`**: `Calculating issuer concentration...`
5.  **`WARN`**: `Unclassified issuer exposure for portfolio E2E_CONC_01 is 15000.00` (Example)
6.  **`INFO`**: `Successfully completed concentration calculation for portfolio E2E_CONC_01`

## 5. Common Failure Scenarios & Resolutions

| Scenario                               | Symptom(s) in API Response                                      | Key Log Message(s) / Metric Alert                             | Resolution / Action                                                                                                             |
| -------------------------------------- | --------------------------------------------------------------- | ------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| **Portfolio Does Not Exist** | `404 Not Found` with detail `"Portfolio P_FAKE not found"`      | `ValueError: Portfolio P_FAKE not found`                      | Verify the `portfolio_id` with the user. The ID is incorrect or has not been ingested via the `ingestion_service`.            |
| **High "Unclassified" Issuer Group** | Issuer concentration contains a large "Unclassified" bucket.    | `Unclassified issuer exposure...` (WARN)                      | This indicates a data quality issue. Advise the user/data team to ingest the missing `instrument` data with issuer IDs.         |
| **High Latency** | API response times are slow.                                    | `concentration_calculation_duration_seconds` is high.         | Check the structured logs for the `correlation_id` to identify slow repository calls. Escalate to developers to analyze query performance. |
| **Calculation Fails Unexpectedly** | `500 Internal Server Error`                                     | `An unexpected error occurred during concentration calculation...` | **Escalate to the development team.** Provide the full logs, `correlation_id`, and the request body that caused the failure.   |