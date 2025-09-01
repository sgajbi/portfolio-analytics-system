# Feature Documentation: The Reprocessing Engine

## 1. Summary

The Reprocessing Engine is the core architectural feature that guarantees data integrity and correctness in the face of **back-dated events**. In financial systems, it's common for transactions or price corrections to arrive days or weeks after they occurred. This engine ensures that the system can automatically and deterministically rebuild a portfolio's history to correctly incorporate this new information without manual intervention.

The entire mechanism is built on a powerful but simple concept: the **Epoch/Watermark Model**.

## 2. The Problem: The Challenge of Back-Dated Data

Imagine a portfolio's history has been calculated up to September 14th. On September 15th, a transaction that occurred on September 12th is ingested. A simple system might just insert this transaction, but all subsequent calculations (positions, performance, etc.) from September 12th onward are now incorrect. The Reprocessing Engine is designed to solve this problem systematically.

## 3. The Solution: Epoch and Watermark

The system explicitly tracks the state of every unique financial time-series, defined by a `(portfolio_id, security_id)` key. This state is managed by two key concepts:

* **Epoch:** An integer version number for the entire history of a key. All correct, current data for a key shares the same epoch.
* **Watermark:** A date that indicates how far forward the system has successfully and contiguously calculated for a key's current epoch.

### How it Works

1.  **Detection:** When a back-dated event (e.g., a transaction on Sept 12th) arrives, the system detects that its date is before the key's current watermark (e.g., Sept 14th).
2.  **Epoch Increment:** The system immediately increments the `epoch` for that specific key (e.g., from `0` to `1`). This acts as a lock and signals that a new, corrected history is being built. The `watermark` is reset to a date just before the back-dated event (Sept 11th).
3.  **Deterministic Replay:** The service that detected the event triggers a replay of all relevant historical events for that key, now tagged with the new epoch (`1`).
4.  **Epoch Fencing:** As the new events flow through the system, all downstream consumers perform a crucial check: they only process messages whose epoch matches the *current* epoch for that key in the central state. Any stray messages from the old epoch (`0`) are safely ignored. This "fencing" is the primary mechanism that prevents data corruption and race conditions.
5.  **Gap Filling:** The `ValuationScheduler` automatically detects the gap between the new, earlier watermark (Sept 11th) and the current business date, creating jobs to rebuild the daily history under the new epoch.
6.  **Completion:** Once the history is fully rebuilt, the key's state is marked as `CURRENT`, and all API queries will atomically switch to reading data from the new, correct epoch.