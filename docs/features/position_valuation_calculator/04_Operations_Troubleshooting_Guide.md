# Operations & Troubleshooting Guide: Position Valuation Calculator

This guide provides operational instructions for monitoring and troubleshooting the `position-valuation-calculator` service.

## 1. Observability & Monitoring

The health of this service is critical for overall data freshness. Monitor the following Prometheus metrics.

### Key Metrics to Watch

* **`valuation_jobs_skipped_total` (Counter):**
    * **What it is:** Increments when a consumer skips a valuation job because no position history was found for the given date. This is often normal behavior for jobs created at the very beginning of a position's life.
    * **What to watch for:** A sudden, large spike might indicate an issue with the upstream `position-calculator`.

* **`valuation_jobs_failed_total` (Counter):**
    * **What it is:** Increments when a consumer permanently fails a job due to missing reference data (e.g., an instrument or FX rate).
    * **What to watch for:** Any increase in this metric requires investigation. This indicates a data dependency issue that is preventing valuation.

* **`scheduler_gap_days` (Histogram):**
    * **What it is:** Measures the gap in days between a position's watermark and the current business date.
    * **What to watch for:** Persistently high values in the upper buckets of this histogram indicate that the system is falling behind on its valuation backfills. This could be a symptom of a slow consumer or a "thundering herd" reprocessing event.

## 2. Structured Logging & Tracing

All logs are structured JSON and tagged with a `correlation_id`. Key log messages can help diagnose issues:

* **`"Back-dated price event detected..."`**: Confirms that the `PriceEventConsumer` has correctly identified a back-dated price and will trigger a reprocessing flow.
* **`"Created ... backfill valuation jobs for ..."`**: Confirms that the `ValuationScheduler` is correctly identifying data gaps and creating work.
* **`"Skipping job due to missing position data..."`**: A common warning from the `ValuationConsumer`. This is expected if the scheduler creates a job for a date before the first transaction.
* **`"Reset ... stale valuation jobs from 'PROCESSING' to 'PENDING'"`**: This message indicates that the scheduler's self-healing mechanism has activated to recover jobs from a potentially crashed consumer.

## 3. Common Failure Scenarios & Resolutions

| Scenario | Symptom(s) | Key Log Message(s) / DB Query | Resolution / Action |
| :--- | :--- | :--- | :--- |
| **Positions Not Valued** | Data in the query APIs is stale. The `daily_position_snapshots` table is not being updated for the current business date. | `SELECT status, count(*) FROM portfolio_valuation_jobs GROUP BY status;` shows a high number of `PENDING` jobs. | **Cause:** The `ValuationScheduler` might not be dispatching jobs, or the consumers might not be processing them. <br> **Resolution:** Check the service logs for errors. If no jobs are being claimed, the scheduler might have an issue. If jobs are `PROCESSING` but not completing, check the consumer logs. |
| **Valuations Failing** | The `valuation_jobs_failed_total` metric is increasing. | `SELECT failure_reason, count(*) FROM portfolio_valuation_jobs WHERE status = 'FAILED' GROUP BY 1;` | **Cause:** Most commonly, this is due to missing reference data like an FX rate or a market price. <br> **Resolution:** Ingest the missing data. **Note:** The system will not automatically re-value these failed records. A manual reprocessing must be triggered via the `tools/reprocess_transactions.py` script for an associated transaction. |
| **Back-dated Price Ignored** | A back-dated price was ingested, but old position values remain unchanged. | No `Back-dated price event detected` log message. The `instrument_reprocessing_state` table is empty for the security. | **Cause:** The `PriceEventConsumer` might be down or failing. <br> **Resolution:** Check the logs for the `position-valuation-calculator`. If there are no obvious errors, restart the service to ensure the consumer is running correctly. |