# Feature Documentation: Position Calculator

## 1. Summary

The **`position_calculator_service`** is a core backend service that transforms the stream of individual, cost-calculated transactions into an auditable, chronological history of each security holding. Its primary output is the `position_history` table, which provides a running statement of quantity and cost basis after every transaction.

This service is also the system's primary defense against out-of-order data. It contains the logic to detect back-dated **transactions** and is responsible for initiating the entire **Epoch/Watermark Reprocessing** flow to ensure the portfolio's history is always accurate and deterministic.

## 2. Key Features

* **Position History Generation:** Consumes enriched transaction events and calculates the resulting position state (quantity and cost basis), creating a new record in `position_history` for each transaction. This provides a complete, auditable trail.
* **Back-dated Transaction Detection:** Contains the critical logic that identifies transactions arriving out of chronological order.
* **Atomic Reprocessing Trigger:** When a back-dated transaction is detected, this service is responsible for triggering a full replay of all historical transactions for that key. This entire trigger process—incrementing the `epoch` and queueing all historical events for re-emission—is performed as a single, atomic database transaction using the **Outbox Pattern**. This guarantees that a position will never be left in a corrupted or unrecoverable `REPROCESSING` state, even if the service crashes.

## 3. Gaps and Design Considerations

* **Flawed Cost Basis Logic for Sales:** The current implementation for reducing cost basis on a `SELL` or `TRANSFER_OUT` transaction uses a **proportional (average cost) approximation**. It calculates the percentage of shares being sold and reduces the total cost basis by that same percentage. This is **logically inconsistent** with the `cost_calculator_service`, which calculates a precise Cost of Goods Sold (COGS) based on the FIFO methodology. This discrepancy will cause the cost basis in `position_history` to drift from the true value of the underlying tax lots over time, representing a significant data integrity issue.