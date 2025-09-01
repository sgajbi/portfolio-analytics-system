# Feature Documentation: Position Valuation Calculator

## 1. Summary

The **`position-valuation-calculator`** is a critical backend service responsible for calculating the daily market value of every position held in every portfolio. It produces the `daily_position_snapshots` table, which is the foundational dataset used by nearly all read-APIs, including Portfolio Summary, Risk Analytics, and Concentration.

The service has two distinct but related responsibilities:

1.  **Calculation:** It consumes `valuation_required` jobs from a Kafka topic. For each job, it fetches the position state, the relevant market price, and any necessary FX rates to calculate the market value and unrealized profit & loss.
2.  **Orchestration (`ValuationScheduler`):** It runs a powerful, built-in background scheduler. This scheduler is the "brain" of the system's data integrity and backfill mechanism. It continuously scans for data gaps, triggers reprocessing for back-dated price events, and creates the `valuation_required` jobs for its own consumers to process.

By combining calculation and orchestration, this service ensures that all portfolio data is consistently valued and automatically corrected when historical data changes.

## 2. Key Features

* **Daily Valuation:** Calculates the mark-to-market value and unrealized P&L for every position.
* **Full Dual-Currency Support:** Correctly handles valuation for securities denominated in a different currency than the portfolio's base currency, fetching and applying the appropriate FX rates.
* **Stateful Scheduling:** The `ValuationScheduler` is the sole authority for creating valuation jobs, preventing duplicate or unnecessary work.
* **Automatic Backfilling:** The scheduler detects gaps in the `daily_position_snapshots` history (caused by back-dated events) and automatically creates the jobs needed to fill them.
* **Back-dated Price Reaction:** Detects when a back-dated market price has been ingested and orchestrates the reprocessing flow to ensure all affected portfolio positions are re-valued.
* **Resilient Job Handling:** Includes logic to reset stale jobs that may have been stuck due to a worker crash, ensuring the pipeline is self-healing.