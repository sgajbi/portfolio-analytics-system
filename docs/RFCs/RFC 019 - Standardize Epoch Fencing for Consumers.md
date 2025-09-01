# RFC 019: Standardize Epoch Fencing for Consumers

* **Status**: Proposed
* **Date**: 2025-09-01

## 1. Summary

Epoch fencing is the most critical pattern for ensuring data integrity in our system, but its implementation is currently manual and duplicated across multiple consumers (`PositionTimeseriesConsumer`, `PositionCalculator` consumer, etc.). This approach is error-prone and adds boilerplate code to every new consumer that needs to be "reprocessing-aware."

This RFC proposes abstracting the epoch fencing logic into a reusable utility within the `portfolio-common` library to improve robustness, reduce code duplication, and simplify developer workflow.

## 2. Gap and Proposed Solution

* **Gap:** Manually re-implementing the logic to fetch the current `PositionState` and compare epoch numbers in every consumer increases the risk of subtle bugs and inconsistencies.
* **Proposal:**
    1.  **Create a Fencing Utility Class:** A new class, `EpochFencer`, will be created in `portfolio-common`. It will be initialized with a database session.
    2.  **Implement a `check` Method:** The class will have a single async method, `check(event)`, which encapsulates the entire fencing logic:
        * Extracts `portfolio_id`, `security_id`, and `epoch` from the event payload.
        * Fetches the current `PositionState` for the key.
        * Performs the comparison (`event.epoch < state.epoch`).
        * If the event is stale, it will automatically log the warning and increment the `epoch_mismatch_dropped_total` metric.
        * It will return a boolean `True` if the message should be processed, and `False` if it should be discarded.
    3.  **Refactor Consumers:** All relevant consumers will be refactored to use this new, standardized utility at the beginning of their `process_message` method.

### Example Usage

```python
// In a consumer's process_message method:
fencer = EpochFencer(db_session)
if not await fencer.check(event):
    # The fencer handles logging and metrics.
    # We just need to acknowledge and exit.
    return

# ... proceed with business logic ...