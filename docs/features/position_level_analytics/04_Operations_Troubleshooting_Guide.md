# Operations & Troubleshooting Guide: Position-Level Analytics

This guide provides operational instructions for monitoring and troubleshooting the `positions-analytics` endpoint within the `query_service`.

## 1. Observability & Monitoring

The service exposes specific Prometheus metrics at the `/metrics` endpoint to monitor the performance and usage of this feature.

### Key Metrics to Watch

* **`position_analytics_duration_seconds` (Histogram):**
    * **What it is:** Measures the end-to-end latency of a full API request to this endpoint, labeled by `portfolio_id`.
    * **What to watch for:** This is the primary KPI for this feature. High latency (e.g., >5 seconds) indicates that the service is performing a very heavy on-the-fly calculation. This is expected for portfolios with a large number of holdings, especially when the `PERFORMANCE` section is requested for long time periods.

* **`position_analytics_section_requested_total` (Counter):**
    * **What it is:** Tracks how many times each individual section (e.g., `VALUATION`, `PERFORMANCE`) has been requested.
    * **What to watch for:** This provides valuable insight into which parts of the feature are most heavily used. If `PERFORMANCE` is requested in nearly every call, it reinforces the need for performance optimizations like caching or pre-calculation.

## 2. Structured Logging & Tracing

All logs from the `query_service` are structured JSON and are tagged with the `correlation_id` of the request. To investigate a slow or failed request, use the `correlation_id` to find all related log messages and trace the duration of the underlying database queries.

## 3. Common Failure Scenarios & Resolutions

| Scenario | Symptom(s) in API / Logs | Key Log Message(s) / Metric Alert | Resolution / Action |
| :--- | :--- | :--- | :--- |
| **High API Latency / Timeout** | `504 Gateway Timeout` or very slow API responses. | `position_analytics_duration_seconds` is high. | **Cause:** The most common cause is requesting the `PERFORMANCE` section for a portfolio with a large number of positions over a long time period (e.g., "Since Inception"). <br> **Resolution:** Advise the client to make more targeted requests. For an initial screen load, they should omit the `PERFORMANCE` section. For performance-specific views, they should request shorter periods (e.g., YTD). Escalate to developers to prioritize performance enhancements (see RFC). |
| **Incorrect Performance or Income** | A user reports that the calculated TWR or income for a position is incorrect. | (No error logs) Query the `position_timeseries` and `cashflows` tables for the specific security and date range. | **Cause:** The issue is almost always incorrect underlying data. The on-the-fly calculation is deterministic; incorrect inputs will produce incorrect outputs. <br> **Resolution:** This indicates an upstream data pipeline issue. The `timeseries_generator_service` or `cashflow_calculator_service` may have generated a bad record. Investigate the health and inputs of those upstream services. |
| **Portfolio Not Found** | `404 Not Found` API response. | `ValueError: Portfolio ... not found` in service logs. | **Cause:** The requested `portfolio_id` does not exist in the database. <br> **Resolution:** Verify the `portfolio_id` with the user. |