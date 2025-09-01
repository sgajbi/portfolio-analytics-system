# RFC 024: Ensure Atomic Portfolio Time-Series Aggregation

* **Status**: Proposed
* **Date**: 2025-09-01

## 1. Summary

A critical data integrity flaw has been identified in the `timeseries_generator_service`. A race condition exists where the portfolio-level aggregation for a given day `D` can be triggered and executed before all of that day's individual `position_timeseries` records have been generated. This results in a permanently incorrect `portfolio_timeseries` record based on a partial set of data, which corrupts all downstream performance and risk analytics.

This RFC proposes a manifest-based approach to solve this race condition by making the aggregation trigger deterministic.

## 2. The Flaw: The Race Condition

1.  The `PositionTimeseriesConsumer` processes a snapshot for `(Portfolio P1, Security S1, Date D)` and creates a `position_timeseries` record. It then idempotently creates a `portfolio_aggregation_job` for `(P1, D)`.
2.  If `P1` has 10 positions on Date `D`, this process will happen 10 times, repeatedly upserting the same `(P1, D)` job.
3.  The `AggregationScheduler` runs on its own schedule. It might claim and dispatch the job for `(P1, D)` after only one of the 10 `position_timeseries` records has been created.
4.  The `PortfolioTimeseriesConsumer` then executes, faithfully aggregating the *one* record it can find, and writes an incorrect `portfolio_timeseries` record to the database. This record is now considered complete, and the error will silently propagate to all analytics.

## 3. Proposed Solution: Manifest-Based Aggregation

To solve this, we must introduce a mechanism that allows the `AggregationScheduler` to know exactly how many `position_timeseries` records are *expected* for a given day before it runs the aggregation.

### 3.1. New Table: `daily_aggregation_manifest`

A new table will be created to track the expected work for each portfolio-day aggregation.

| Column | Type | Description |
| :--- | :--- | :--- |
| `portfolio_id` | `VARCHAR` (PK) | The portfolio's unique identifier. |
| `aggregation_date` | `DATE` (PK) | The date for the aggregation. |
| `expected_count` | `INTEGER` | The number of `position_timeseries` records that must exist before this aggregation can run. |
| `status` | `VARCHAR` | `PENDING`, `COMPLETE`. |

### 3.2. Logic Changes

1.  **Manifest Creation (`position-valuation-calculator`):** The responsibility for knowing how many positions exist on a given day lies with the `ValuationScheduler`. When it creates the valuation jobs for a portfolio for day `D`, it already knows the exact number of open positions. At this point, it will also be modified to create or update the manifest record in `daily_aggregation_manifest`, setting the `expected_count`.

2.  **Modify Scheduler Eligibility (`timeseries_generator_service`):** The `find_and_claim_eligible_jobs` method in the `TimeseriesRepository` will be significantly enhanced. Before claiming a `portfolio_aggregation_job` for `(P1, D)`, it will perform a new check:
    * It will query the `daily_aggregation_manifest` to get the `expected_count`.
    * It will perform a `COUNT(*)` on the `position_timeseries` table for `(P1, D)`.
    * The job for `(P1, D)` will only be considered eligible if the actual count matches the expected count.

### Consequences

* **Pros:**
    * **Guaranteed Correctness:** This solution completely eliminates the race condition and guarantees that portfolio-level aggregation only runs when all its constituent data is present.
    * **Determinism:** The system's behavior becomes deterministic and auditable.
* **Cons:**
    * **Increased Complexity:** This introduces a new table and adds logic to the `ValuationScheduler`. This is a necessary trade-off for data integrity.

## 4. Acceptance Criteria

* The `daily_aggregation_manifest` table is created.
* The `ValuationScheduler` is updated to create manifest records.
* The `AggregationScheduler`'s eligibility query is updated to use the manifest.
* A new E2E test is created that proves the aggregation for a portfolio with multiple positions only runs after all `position_timeseries` records for that day are generated.