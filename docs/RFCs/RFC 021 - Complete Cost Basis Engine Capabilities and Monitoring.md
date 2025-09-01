# RFC 021: Complete Cost Basis Engine Capabilities and Monitoring

* **Status**: Proposed
* **Date**: 2025-09-01

## 1. Summary

The `cost_calculator_service` and its underlying `financial-calculator-engine` are functioning correctly for the FIFO methodology. However, to be a gold-standard system, it must support other common cost basis methods and provide better visibility into its most performance-intensive operations.

This RFC proposes two enhancements:
1.  Fully implement the **Average Cost (AVCO)** basis methodology within the `financial-calculator-engine`, making it a selectable strategy.
2.  Introduce new, specific Prometheus metrics to monitor the depth and latency of the full history recalculation process.

## 2. Gaps and Proposed Solutions

### 2.1. Feature Gap: Incomplete Cost Basis Methodologies

* **Gap:** The `financial-calculator-engine` currently contains a stub for an `AverageCostBasisStrategy` but it is incomplete and not safe for use, particularly in dual-currency scenarios. This limits the system to only supporting FIFO, which may not meet the accounting requirements for all clients or jurisdictions.
* **Proposal:**
    1.  **Fully Implement `AverageCostBasisStrategy`:** Refactor the existing class to correctly handle dual-currency cost tracking. It must maintain the running average cost per share in both the instrument's local currency and the portfolio's base currency.
    2.  **Introduce Configuration:** The system needs a mechanism to select which cost basis method to use. This should be added as a new, optional field on the `portfolios` table (e.g., `cost_basis_method`).
    3.  **Update `CostCalculator`:** The `CostCalculatorConsumer` will be modified to read this portfolio-level configuration and instantiate the appropriate strategy (FIFO or AVCO) from a strategy factory for each transaction it processes.

### 2.2. Monitoring Gap: Lack of Recalculation Metrics

* **Gap:** The service's most computationally expensive operation is the full history recalculation. We currently have no specific metrics to monitor how deep these recalculations are (i.e., how many historical transactions are replayed) or how long they take. This makes it difficult to diagnose performance bottlenecks or plan for capacity.
* **Proposal:**
    1.  **Add `recalculation_depth` Metric:** Introduce a new Prometheus `Histogram` to track the number of historical transactions fetched and replayed for each incoming event. This will give us insight into the typical "depth" of our recalculations.
    2.  **Add `recalculation_duration_seconds` Metric:** Introduce a new Prometheus `Histogram` to specifically measure the wall-clock time spent inside the `TransactionProcessor.process_transactions` method. This will isolate the performance of the core financial engine from Kafka communication and database I/O.