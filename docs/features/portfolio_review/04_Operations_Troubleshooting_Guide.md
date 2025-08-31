# Operations & Troubleshooting Guide: Portfolio Review

## 1. Summary

This guide provides operational instructions for monitoring and troubleshooting the `POST /portfolios/{portfolio_id}/review` endpoint. Because this feature is a server-side orchestrator, its health is directly dependent on the health of its sub-services.

## 2. Key Dependencies

A failure in the `/review` endpoint is almost always a symptom of a failure in one of its underlying dependencies. When troubleshooting, investigate these services first.

* `PortfolioService`
* `SummaryService`
* `PerformanceService`
* `RiskService`
* `PositionService`
* `TransactionService`

All these services reside within the `query-service` pod and depend on a healthy connection to the **PostgreSQL read-replica database**.

## 3. Observability & Monitoring

The feature exposes a key Prometheus metric via the `query-service`'s `/metrics` endpoint. This should be monitored to understand usage and performance.

| Metric Name                           | Type      | Labels         | Description & What to Watch For                                                                                             |
| ------------------------------------- | --------- | -------------- | --------------------------------------------------------------------------------------------------------------------------- |
| `review_generation_duration_seconds`  | `Histogram` | `portfolio_id` | **Primary KPI.** Measures the end-to-end latency of a full report generation. Spikes indicate a performance issue in one of the underlying services or a database query. |

## 4. Structured Logging & Tracing

All logs related to a single API request are tied together with a `correlation_id`. When troubleshooting, always find the `correlation_id` from the `X-Correlation-ID` response header or the logs.

**Example Log Flow for a Request:**

1.  **`INFO`**: `Generating review for portfolio E2E_REVIEW_01` (entry point).
2.  **(Parallel Execution)**: Multiple `INFO` logs from the sub-services (e.g., `Starting summary calculation...`, `Calculating performance...`).
3.  **`INFO`**: `Successfully completed review generation for portfolio E2E_REVIEW_01` (exit point).

The total time between the first and last log entry for a given `correlation_id` should approximate the value recorded in the `review_generation_duration_seconds` histogram.

## 5. Common Failure Scenarios & Resolutions

| Scenario                                                     | Symptom(s) in API Response                                                                          | Key Log Message(s) / Metric Alert                                 | Resolution / Action                                                                                                                                                                                                   |
| ------------------------------------------------------------ | --------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Portfolio Does Not Exist** | `404 Not Found` with detail `"Portfolio P_FAKE not found"`                                          | `ValueError: Portfolio P_FAKE not found` from `PortfolioService`  | Verify the `portfolio_id` with the user. The ID in the URL is incorrect or has not yet been ingested and persisted.                                                                                               |
| **Data Missing for a Section** | Report generates successfully but a section is empty when data is expected (e.g., `performance` is null). | (No error logs)                                                   | This indicates an issue in an upstream data pipeline. For example, if `portfolio_timeseries` data is missing, the `PerformanceService` will correctly return no results. Trace the data flow for the missing entity. |
| **High Latency** | API response times are slow.                                                                        | `review_generation_duration_seconds` is high.                     | Check the structured logs for the `correlation_id` to see which sub-service call is taking the longest. Investigate the performance of that specific service and its underlying database queries.                    |
| **Calculation Fails Unexpectedly** | `500 Internal Server Error`                                                                         | `An unexpected error occurred during review generation...`        | **Escalate to the development team.** Provide the full logs, `correlation_id`, and the request body that caused the failure. This indicates an unhandled exception in one of the sub-services.                     |
```
