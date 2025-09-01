# Operations & Troubleshooting Guide: Cashflow Calculator

This guide provides operational instructions for monitoring and troubleshooting the `cashflow_calculator_service`.

## 1. Observability & Monitoring

The service is a standard Kafka consumer and exposes metrics via its `/metrics` endpoint.

### Key Metrics to Watch

* **Consumer Lag:** High or growing consumer lag on the `raw_transactions_completed` topic indicates that the service cannot keep up with the volume of incoming transactions. This could be due to a performance bottleneck or persistent errors causing messages to be retried.
* **`events_processed_total` (Counter):** Tracks the number of transactions successfully processed. A flat line on this metric when there is known traffic indicates the service is stuck or failing.
* **`events_dlqd_total` (Counter):** Tracks the number of messages sent to the Dead-Letter Queue. Any increase in this metric requires immediate investigation, as it signifies a "poison pill" message that could not be processed.

## 2. Structured Logging & Tracing

All logs are structured JSON and are tagged with the `correlation_id` of the original ingestion request. When investigating an incorrect performance figure downstream, you can find the `transaction_id` causing the issue and use it to find the corresponding `correlation_id` in the `cashflow_calculator_service` logs to see exactly how its cash flow was generated.

A key log message to look for is: `Calculated cashflow for txn ...`. This confirms that a transaction was processed and shows the resulting amount and classification.

## 3. Common Failure Scenarios & Resolutions

| Scenario | Symptom(s) in API / Logs | Key Log Message(s) / DB Query | Resolution / Action |
| :--- | :--- | :--- | :--- |
| **Incorrect Performance (TWR)** | Downstream performance reports show incorrect TWR figures that don't align with client contributions. | (No error logs) Query the `cashflows` table for the portfolio and period in question. | **Cause:** The issue is almost always a misclassified cash flow. For example, a fee might be incorrectly marked as `is_portfolio_flow=False`. <br> **Resolution:** 1. Query the `cashflows` table to find the incorrect record. 2. Trace its `transaction_id` back to the original transaction. 3. Escalate to the development team to correct the rule in `cashflow_config.py`. 4. Manually reprocess the original transaction to regenerate the correct cash flow. |
| **Messages Sent to DLQ** | The `events_dlqd_total` metric is increasing. | `Message validation failed... Sending to DLQ.` | **Cause:** A "poison pill" message. This most commonly occurs if a new `transaction_type` is introduced without a corresponding rule in the `cashflow_config.py` map. <br> **Resolution:** **Escalate to the development team.** Provide the full DLQ message, which contains the original transaction and a detailed error traceback. |
| **High Consumer Lag** | Kafka consumer lag is high and growing. | `DB integrity error; will retry...` appears frequently in logs. | **Cause:** The service is likely stuck in a retry loop due to a transient database issue (e.g., connection problems, deadlocks). <br> **Resolution:** Check the health of the PostgreSQL database. The consumer should recover automatically once the database is healthy. |

## 4. Gaps and Design Considerations

* **Missing Metrics:** The service lacks specific metrics for the business logic it performs. There is no visibility into the *types* of cashflows being created. Adding a Prometheus counter with a `classification` label would provide valuable insight into the nature of the transactions flowing through the system (e.g., are we processing more deposits or withdrawals today?).