# Operations & Troubleshooting Guide: Position Calculator

This guide provides operational instructions for monitoring and troubleshooting the `position_calculator_service`.

## 1. Observability & Monitoring

The health of this service is crucial for both data accuracy and the proper functioning of the reprocessing engine.

### Key Metrics to Watch

| Metric Name | Type | Labels | Description & What to Watch For |
| :--- | :--- | :--- | :--- |
| **`reprocessing_epoch_bumped_total`** | **Counter** | `portfolio_id`, `security_id` | **(New)** Increments every time a back-dated transaction triggers a new epoch and a full reprocessing flow. This is the primary indicator of reprocessing activity. |
| `epoch_mismatch_dropped_total` | Counter | `service_name`, `topic`, `portfolio_id`, `security_id` | Increments every time this consumer discards a Kafka message because its epoch is stale. A high rate indicates that epoch fencing is working correctly to prevent data corruption during an active replay. |
| `event_processing_latency_seconds` | Histogram | `topic`, `consumer_group` | Measures the time taken to process a single transaction. A sudden increase can indicate that the service is recalculating very long position histories, which may be a performance bottleneck. |
| Consumer Lag | Gauge | `topic`, `group_id`, `partition` | High or growing consumer lag on the `processed_transactions_completed` topic is a primary indicator that the service is struggling to keep up with the transaction volume or is stuck in a retry loop. |

## 2. Structured Logging & Tracing

All logs are structured JSON and are tagged with the `correlation_id`. The most important log message from this service is:

* **`"Back-dated transaction detected. Triggering reprocessing flow."`**: This confirms that the service has correctly identified an out-of-order transaction and has initiated the epoch increment and event replay process.

## 3. Common Failure Scenarios & Resolutions

| Scenario | Symptom(s) in API / Logs | Key Log Message(s) / DB Query | Resolution / Action |
| :--- | :--- | :--- | :--- |
| **Position History is Incorrect** | Downstream data (e.g., in the `/positions` API) shows the wrong quantity or cost basis. | (No error logs) Query the `position_history` table for the affected security. | **Cause:** The `cost_calculator_service` may have provided an incorrect `net_cost` on the inbound transaction event. <br> **Resolution:** Verify the cost basis logic in the upstream service. This service now correctly applies the authoritative `net_cost` provided to it. |
| **Reprocessing Not Triggered** | A known back-dated transaction was ingested, but the `epoch` in the `position_state` table did not increment. | No "Back-dated transaction detected" log message. `reprocessing_epoch_bumped_total` metric is not incremented. | **Cause:** The back-dated detection logic did not evaluate to `true`. This could be because the `watermark_date` and latest `daily_position_snapshot` were both older than the transaction date. <br> **Resolution:** 1. Query `position_state` and `daily_position_snapshots` for the key to verify the dates. 2. If the state appears correct, this may indicate a subtle logic issue. Escalate to the development team with the transaction details. |
| **Messages Sent to DLQ** | The `events_dlqd_total` metric is increasing. | `Unexpected error in position calculator...` | **Cause:** A "poison pill" message caused by a bug in the position calculation logic that isn't handled gracefully. <br> **Resolution:** **Escalate to the development team.** Provide the full DLQ message, which contains the original transaction and a detailed error traceback. |