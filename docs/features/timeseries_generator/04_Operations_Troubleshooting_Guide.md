# Operations & Troubleshooting Guide: Timeseries Generator

This guide provides operational instructions for monitoring and troubleshooting the `timeseries_generator_service`.

## 1. Observability & Monitoring

The health of this service is critical for the availability of all performance and risk analytics.

### Key Metrics to Watch

* **Consumer Lag:** Monitor consumer lag on both primary topics:
    * `daily_position_snapshot_persisted`: High lag here indicates the service is failing to generate the base `position_timeseries` records.
    * `portfolio_aggregation_required`: High lag here indicates the service is failing to perform the final portfolio-level aggregation.
* **`events_dlqd_total` (Counter):** An increase in this metric signifies a "poison pill" message that could not be processed, likely due to a persistent error like a missing FX rate.
* **`event_processing_latency_seconds` (Histogram):** A sudden increase in the latency for the `portfolio_aggregation_required` consumer can indicate that it is processing portfolios with a very large number of positions.

## 2. Structured Logging & Tracing

All logs are structured JSON and are tagged with the `correlation_id`. Key log messages can help diagnose issues:

* **`"Processing position snapshot for..."`**: Confirms the `PositionTimeseriesConsumer` is running.
* **`"Received aggregation job for..."`**: Confirms the `PortfolioTimeseriesConsumer` is running.
* **`"Missing FX rate from..."`**: A critical error from the portfolio aggregation logic that will cause the job to fail and the message to be sent to the DLQ.
* **`"Scheduler claimed ... jobs for processing"`**: Confirms that the `AggregationScheduler` is active and dispatching work.

## 3. Common Failure Scenarios & Resolutions

| Scenario | Symptom(s) in API / Logs | Key Log Message(s) / DB Query | Resolution / Action |
| :--- | :--- | :--- | :--- |
| **Incorrect Performance/Risk Figures** | TWR or Risk metrics from the `query_service` are incorrect (e.g., unexpectedly low market value). | (No error logs) Query `portfolio_timeseries` for the affected day and compare the `eod_market_value` to the sum of `market_value` from `daily_position_snapshots`. | **Cause:** This is a symptom of the known data integrity gap. The portfolio aggregation job likely ran on an incomplete set of that day's `position_timeseries` data. <br> **Resolution:** 1. Manually delete the incorrect row from `portfolio_timeseries`. 2. Manually update the corresponding `portfolio_aggregation_jobs` record status back to `PENDING`. The scheduler will then re-claim and re-run the job correctly once all position data is present. Escalate to developers to prioritize the RFC to fix this race condition. |
| **Analytics Data is Stale** | Performance and risk data is not available for the latest business date. | `SELECT * FROM portfolio_aggregation_jobs WHERE status = 'PENDING' ORDER BY aggregation_date;` shows jobs are not being processed. | **Cause:** The scheduler's eligibility logic is preventing jobs from being claimed. This almost always means the previous day's `portfolio_timeseries` record is missing, breaking the chain. <br> **Resolution:** Investigate why the previous day's job did not complete. Check the job status and service logs for that day. |
| **Aggregation Jobs are Failing** | The `events_dlqd_total` metric is increasing for the `portfolio_aggregation_required` consumer. | `FxRateNotFoundError` in the logs. | **Cause:** The portfolio aggregation logic requires an FX rate to convert a position's cash flows, but the rate is not in the database for that day. <br> **Resolution:** Ingest the missing FX rate data. Then, replay the message from the DLQ using the `tools/dlq_replayer.py` script. |

## 4. Gaps and Design Considerations

* **Missing Metrics:** The service lacks specific metrics for its core functions. There is no visibility into how many position vs. portfolio time-series records are created, or how long the portfolio-level aggregation takes. This makes it difficult to diagnose performance issues.