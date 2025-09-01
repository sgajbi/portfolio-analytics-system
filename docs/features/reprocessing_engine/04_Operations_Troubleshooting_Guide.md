# Operations & Troubleshooting Guide: Reprocessing Engine

This guide provides operational instructions for monitoring and troubleshooting the reprocessing engine.

## 1. Observability & Monitoring

The health and progress of the reprocessing engine can be monitored via key Prometheus metrics and direct database queries.

### Key Metrics to Watch

* **`reprocessing_active_keys_total` (Gauge):**
    * **What it is:** The total number of `(portfolio_id, security_id)` keys currently in the `REPROCESSING` state.
    * **What to watch for:** This number should ideally be low or zero. A value that is persistently high or constantly growing indicates a systemic issue, such as a failing consumer or a "thundering herd" of back-dated events.

* **`scheduler_gap_days` (Histogram):**
    * **What it is:** Measures the gap in days between a key's `watermark_date` and the current business date when the `ValuationScheduler` runs.
    * **What to watch for:** Large gaps indicate that the valuation backfill process is lagging. This could be due to a slow consumer or an overwhelming number of jobs.

* **`epoch_mismatch_dropped_total` (Counter):**
    * **What it is:** A counter that increments every time a consumer discards a Kafka message because its epoch is stale.
    * **What to watch for:** A consistently high rate of dropped messages can indicate a "split-brain" scenario or a misbehaving producer that is still publishing events with an old epoch.

## 2. Direct Database Monitoring

The most direct way to investigate an issue is to query the `position_state` table.

```sql
-- Find keys that have been stuck in reprocessing for more than 1 hour
SELECT portfolio_id, security_id, epoch, watermark_date, updated_at
FROM position_state
WHERE status = 'REPROCESSING'
AND updated_at < NOW() - INTERVAL '1 hour';
````

## 3\. Common Failure Scenarios & Resolutions

| Scenario | Symptom(s) | Key Log Message(s) / Metric Alert | Diagnosis & Resolution |
| :--- | :--- | :--- | :--- |
| **Stuck Reprocessing** | Data for a specific position is not updating. | `reprocessing_active_keys_total` is \> 0. The `position_state` table shows a key stuck in `REPROCESSING`. | **Cause:** A consumer in the pipeline is failing, or the `position-calculator` crashed mid-replay. \<br\> **Resolution:** Check the logs for the failing consumer. If the cause was a transient issue that has been resolved, you can manually trigger a new reprocessing flow for the original back-dated transaction using the `tools/reprocess_transactions.py` script. |
| **Thundering Herd** | `scheduler_gap_days` is high and growing. `reprocessing_active_keys_total` is very high. | `Back-dated price event detected...` appears frequently in `position-valuation-calculator` logs. | **Cause:** A back-dated price was ingested for a widely-held security, triggering a massive number of watermark resets. The system is struggling to keep up. \<br\> **Resolution:** This is a scalability challenge. The system will eventually catch up, but may require scaling up the consumer instances for the calculator services. |
| **Stale Data on API** | A user reports seeing old data for a position. | `epoch_mismatch_dropped_total` is increasing for the affected key. | **Cause:** The `position_state` has moved to a new epoch, but a producer is still emitting messages with the old epoch. \<br\> **Resolution:** Identify the misbehaving producer from the logs and restart it. The epoch fencing is working as designed by protecting the database, but the root cause must be fixed. |

```
```