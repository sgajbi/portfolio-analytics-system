# RFC 022: Enhance Cashflow Calculator Configurability and Monitoring

* **Status**: Proposed
* **Date**: 2025-09-01

## 1. Summary

The `cashflow_calculator_service` is currently simple and robust. However, its business logic is hardcoded, and it lacks specific metrics for operational insight. This makes it inflexible to business rule changes and creates a blind spot in our monitoring.

This RFC proposes two enhancements:
1.  Externalize the transaction-to-cashflow rule set from the code into a database table to allow for dynamic configuration without requiring a new deployment.
2.  Introduce a new Prometheus metric to provide a granular count of the different types of cashflows being generated.

## 2. Gaps and Proposed Solutions

### 2.1. Inflexibility: Hardcoded Business Logic

* **Gap:** The mapping of transaction types to cashflow characteristics is defined in a static Python dictionary (`CASHFLOW_CONFIG`). If a business analyst needs to change a rule (e.g., reclassify a specific fee to no longer be a portfolio-level flow), it requires a developer to change the code, run tests, and redeploy the service.
* **Proposal:**
    1.  **Create `cashflow_rules` Table:** A new database table will be created to store the mapping.
        | Column | Type | Description |
        | :--- | :--- | :--- |
        | `transaction_type` | `VARCHAR` (PK) | e.g., "BUY", "FEE" |
        | `classification` | `VARCHAR` | e.g., "INCOME" |
        | `timing` | `VARCHAR` | "BOD" or "EOD" |
        | `is_position_flow` | `BOOLEAN` | |
        | `is_portfolio_flow` | `BOOLEAN` | |
    2.  **Modify Service Startup:** The `cashflow_calculator_service` will be modified to query this table on startup and load the rules into an in-memory dictionary, caching them for the lifetime of the process.
    3.  **Graceful Fallback:** If a transaction is received for a type not in the database rules, the service will log a critical error and send the message to the DLQ.

### 2.2. Monitoring Gap: Lack of Business-Level Metrics

* **Gap:** We can monitor the *technical* health of the consumer (lag, processing time), but we have no insight into the *business* activity it's processing. We cannot easily answer questions like, "Are we processing more deposits or withdrawals today?" or "Have we processed any dividend cashflows this hour?".
* **Proposal:**
    1.  **Add `cashflows_created_total` Metric:** Introduce a new Prometheus `Counter` metric.
    2.  **Add Labels:** This metric will have `classification` and `timing` labels.
    3.  **Instrument the Logic:** The `CashflowLogic` class will be updated to increment this counter after successfully generating a cashflow record. For example: `METRIC.labels(classification="INCOME", timing="EOD").inc()`. This provides immediate, granular insight into the service's workload.