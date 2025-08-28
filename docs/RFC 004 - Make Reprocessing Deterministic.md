# RFC 004: Make Reprocessing Deterministic

  * **Date**: 2025-08-28
  * **Services Affected**: `position-calculator`, `position-valuation-calculator`

## 1\. Summary (TL;DR)

The detection of back-dated transactions is currently unreliable, preventing the system from correctly triggering reprocessing. The detector in `position-calculator` relies exclusively on `position_state.watermark_date`, which for new or rarely-traded keys, often remains at its default `1970-01-01` value. The `ValuationScheduler` is responsible for advancing this watermark, but its cycle may not complete before a back-dated message is consumed. This timing dependency causes the detector to incorrectly classify back-dated events as current, keeping all calculations stuck in `epoch 0` and leading to data integrity issues and test failures.

This RFC proposes a three-part solution:

1.  **Harden the back-dated event detector** in `position-calculator` to use the latest completed `DailyPositionSnapshot` date as the primary source of truth for an epoch's progress, falling back to the watermark only if necessary.
2.  **Improve the reliability and observability of the `ValuationScheduler`** to ensure it consistently advances watermarks and logs its progress.
3.  **Formalize epoch propagation** in all relevant Kafka events to guarantee strict data fencing during a replay.

## 2\. Motivation & Evidence

The primary motivation is to fix a critical bug preventing our reprocessing and back-dating functionality from working as designed. The evidence from logs and failing E2E tests (`test_reprocessing_workflow.py`, `test_rapid_reprocessing.py`) is conclusive:

  * **Epoch Stuck at 0**: Despite ingesting transactions that are clearly back-dated relative to other data, `position_state.epoch` never increments beyond 0.
  * **Incorrect Data**: Downstream artifacts like daily snapshots and time series are generated in `epoch 0` for the back-fill window, which is incorrect. A new epoch should have been created for the replay.
  * **Root Cause**: The detector logic `transaction_date <= watermark_date` returns `false` because `watermark_date` is `1970-01-01` at the time of evaluation. The system proceeds as if the event were current.

The goal is to create a **deterministic** system where a back-dated event *always* triggers a new epoch, regardless of the `ValuationScheduler`'s operational timing.

## 3\. Proposed Technical Changes

### 3.1. Harden the Back-Dated Detector (`position-calculator`)

The core of the problem lies in the `transaction_event_consumer`. We will modify its logic to be resilient to watermark lag.

**Change**:
Before processing a `processed_transactions_completed` event, the consumer will determine the `effective_completed_date` for the given key (`portfolio_id`, `security_id`) and its current `epoch` using the following priority:

1.  Query for the `MAX(date)` from the `daily_position_snapshots` table for the key's current epoch.
2.  If no snapshots exist for that epoch, fall back to using the `position_state.watermark_date`.

A transaction will be considered **back-dated** if `transaction.transaction_date <= effective_completed_date`.

**Implementation**:
A new read-only method will be added to `PositionRepository` in `position_calculator`:

```python
# src/services/calculators/position_calculator/app/repositories/position_repository.py

async def get_latest_completed_snapshot_date(
    self, portfolio_id: str, security_id: str, epoch: int
) -> Optional[date]:
    """
    Finds the latest date for which a daily snapshot has been successfully
    created for a given key in a specific epoch.
    """
    # SQL: SELECT max(date) FROM daily_position_snapshots
    #      WHERE portfolio_id=? AND security_id=? AND epoch=?
```

This removes the timing dependency on the `ValuationScheduler`. Snapshot creation is the ground truth of "work completed" for an epoch.

### 3.2. Make Watermark Advancement Reliable (`position-valuation-calculator`)

While 3.1 fixes the immediate bug, the `ValuationScheduler` must still fulfill its design mandate.

**Change**:

1.  Ensure the scheduler's main loop **always** attempts to advance watermarks for keys it has processed after checking for contiguous snapshot completion. This operation must be part of the same transaction as updating job statuses to prevent partial state updates.
2.  Add structured, high-visibility logging to prove this operation is succeeding. A single `INFO` log per batch is sufficient:
    `ValuationScheduler: Advanced N watermarks. Examples: [(p_id, s_id) -> YYYY-MM-DD, ...]`

This change provides operational proof and makes the system robust even if the detector hardening in 3.1 were not present.

### 3.3. Fence and Propagate Epoch on Pipeline Events

To prevent data from a previous epoch from contaminating a new replay, we must ensure the `epoch` is treated as a fencing token throughout the pipeline.

**Change**:

1.  The `position-calculator`, when it triggers a replay, will re-emit all historical `processed_transactions_completed` events. Each re-emitted event payload **must** now include the new `epoch` number.
2.  All consumers of `processed_transactions_completed` (including `position-calculator` itself) **must** compare the `epoch` from the incoming message payload against the current `epoch` for that key in the `position_state` table.
3.  If `message.epoch < position_state.epoch`, the message is stale and **must** be discarded. A metric (`reprocessing_epoch_mismatch_dropped_total`) will be incremented.

This guarantees that once an epoch is incremented to `N+1`, no stray messages from epoch `N` can affect the state.

## 4\. Database Changes

No schema changes are required. However, to support the new lookup in Change 3.1, an index is recommended to ensure performance.

  * **Add Index**: A non-unique index should be created on the `daily_position_snapshots` table to optimize the `MAX(date)` query.
      * **Index on**: `(portfolio_id, security_id, epoch, date)`

## 5\. Rollout & Validation Plan

1.  **Code & Unit Tests**: Implement the changes for 3.1, 3.2, and 3.3. Add unit tests verifying the new `effective_completed_date` logic and the epoch fencing in consumers.
2.  **Observability**: Add the following Prometheus metrics:
      * `reprocessing_epoch_bumped_total`: A counter incremented by `position-calculator` when it triggers a new epoch.
      * `position_state_watermark_lag_days`: A gauge updated periodically by `ValuationScheduler` showing the difference between the current business date and the watermarks it's advancing.
3.  **Validation**: The three failing E2E tests (`test_reprocessing_workflow.py`, `test_rapid_reprocessing.py`, `test_failure_scenarios.py`) will be used as the ultimate validation. Once these changes are deployed, the tests are expected to pass.

## 6\. Acceptance Criteria

  * Ingesting a back-dated transaction for a key with existing daily snapshots **always** triggers an epoch increment and a full, correct replay under the new epoch.
  * The `ValuationScheduler` logs regularly contain "Advanced N watermarks" messages during steady-state operation.
  * All target E2E tests pass.

 