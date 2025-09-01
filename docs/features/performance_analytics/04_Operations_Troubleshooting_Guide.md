# Operations & Troubleshooting Guide: Performance Analytics

This guide provides operational instructions for monitoring and troubleshooting the on-the-fly performance analytics endpoints within the `query_service`.

## 1. Observability & Monitoring

The service exposes standard API metrics via the `/metrics` endpoint.

### Key Metrics to Watch

* **API Request Rate & Latency (`http_requests_total`, `http_request_latency_seconds`):**
    * **What it is:** Standard RED metrics for the `/performance` and `/performance/mwr` endpoints.
    * **What to watch for:** A spike in latency for these specific endpoints can indicate that the service is processing requests for very long date ranges, which require fetching and processing a large amount of time-series data.

* **Database Latency (`db_operation_latency_seconds`):**
    * **What it is:** Measures the latency of database calls made by the service's repositories.
    * **What to watch for:** High latency on queries from the `PerformanceRepository` is the most likely cause of slow API response times.

## 2. Structured Logging & Tracing

All logs from the `query_service` are structured JSON and are tagged with the `correlation_id` of the request. To investigate a specific performance calculation, use the `correlation_id` from the API response header to find all related log messages, including the exact start and end dates used and the duration of the database queries.

## 3. Common Failure Scenarios & Resolutions

| Scenario | Symptom(s) in API / Logs | Key Log Message(s) / DB Query | Resolution / Action |
| :--- | :--- | :--- | :--- |
| **Portfolio Not Found** | `404 Not Found` API response. | `ValueError: Portfolio ... not found` in service logs. | **Cause:** The requested `portfolio_id` does not exist in the database. <br> **Resolution:** Verify the `portfolio_id` with the user. |
| **Empty Performance Result** | `200 OK` API response, but the `summary` object is empty (`{}`). | (No error logs) | **Cause:** This is expected behavior when there is no `portfolio_timeseries` data available for the requested portfolio and date range. <br> **Resolution:** This indicates an upstream data pipeline issue. The `timeseries_generator_service` has either not run for this period or has failed. Investigate the status of that service and its upstream dependencies. |
| **Incorrect Performance Figures** | A user reports that the calculated TWR or MWR does not match their expectations. | (No error logs) `SELECT * FROM portfolio_timeseries WHERE portfolio_id = '...' AND date BETWEEN '...' AND '...';` | **Cause:** The issue is almost always incorrect underlying data in the `portfolio_timeseries` table. The on-the-fly calculation is deterministic; incorrect inputs will produce incorrect outputs. <br> **Resolution:** Query the `portfolio_timeseries` table for the period in question. Manually verify the `bod_market_value`, `eod_market_value`, and cash flow columns. If they are incorrect, the issue must be traced further upstream to the `timeseries_generator_service` or its inputs. |

## 4. Gaps and Design Considerations

* **Missing Specific Metrics:** The service lacks granular metrics for the performance endpoints. It is not possible to distinguish the latency of a TWR vs. an MWR calculation, nor can we track which period types (e.g., YTD, MTD) are most frequently requested. This makes detailed performance tuning and usage analysis difficult.