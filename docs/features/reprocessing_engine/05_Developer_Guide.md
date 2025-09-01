# Developer's Guide: Reprocessing Engine

This guide provides developers with the necessary patterns and best practices for building services that are compatible with the reprocessing engine. Adherence to these patterns is critical for maintaining system-wide data integrity.

## 1. The Cardinal Rule: Epoch Fencing

Any consumer that processes events related to a specific `(portfolio_id, security_id)` key **must** perform epoch fencing before acting on the message. This prevents stale events from a previous, now-obsolete history from corrupting the new, correct history.

### Implementation Pattern

The `position_timeseries_consumer` provides a clear example of this pattern:

```python
// In the consumer's process_message method:

// 1. Get the current state from the central table
state = await position_state_repo.get_or_create_state(event.portfolio_id, event.security_id)

// 2. Compare the message epoch to the current state's epoch
if event.epoch < state.epoch:
    # Increment a metric for observability
    EPOCH_MISMATCH_DROPPED_TOTAL.labels(...).inc()
    
    # Log and discard the message
    logger.warning("Snapshot event has stale epoch. Discarding.")
    return # Acknowledge the message without processing

# 3. If the check passes, proceed with business logic
...
````

## 2\. Writing Reprocessing-Aware Services

When building a new service that creates or modifies historical data, follow this checklist:

  * **Data Model:** If you are creating a new table that stores historical, auditable data related to a `(portfolio_id, security_id)` key, it **must** have an `epoch` column.
  * **Unique Constraints:** Any unique constraints on your new table (e.g., `UNIQUE(portfolio_id, security_id, date)`) **must** be expanded to include the `epoch` (e.g., `UNIQUE(portfolio_id, security_id, date, epoch)`). This allows new and old versions of a record to coexist.
  * **Consumers:** Any consumer in your service that processes versioned events **must** implement the epoch fencing pattern described above.
  * **Repositories:** Any repository method that queries for historical data (e.g., `get_snapshots_for_date_range`) **must** join with the `position_state` table and filter its results on `table.epoch = position_state.epoch`. This ensures that service logic and API queries only ever see data from the latest correct version of history.

<!-- end list -->
 