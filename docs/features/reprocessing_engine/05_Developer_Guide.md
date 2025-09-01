# Developer's Guide: Reprocessing Engine

This guide provides developers with the necessary patterns and best practices for building services that are compatible with the reprocessing engine. Adherence to these patterns is critical for maintaining system-wide data integrity.

## 1. The Cardinal Rule: Epoch Fencing

Any consumer that processes events related to a specific `(portfolio_id, security_id)` key **must** perform epoch fencing before acting on the message. This prevents stale events from a previous, now-obsolete history from corrupting the new, correct history.

To make this process robust and simple, the system provides a reusable utility: `EpochFencer`.

### Implementation Pattern

The `EpochFencer` class in `portfolio-common` abstracts all the necessary logic. All new consumers that handle versioned data must use it at the beginning of their `process_message` method.

```python
# In a consumer's process_message method:
from portfolio_common.reprocessing import EpochFencer
from portfolio_common.db import get_async_db_session

# ...

async def process_message(self, msg: Message):
    # ... deserialize event ...
    
    async for db in get_async_db_session():
        async with db.begin():
            # ... setup repositories
            
            # 1. Instantiate the fencer with the DB session
            # The service_name is used for labeling metrics.
            fencer = EpochFencer(db, service_name="my-new-service")

            # 2. Perform the check
            if not await fencer.check(event):
                # The fencer handles all logging and metrics for dropped messages.
                # Simply acknowledge the message by returning.
                return

            # 3. If the check passes, proceed with business logic
            # ...
````

## 2\. Writing Reprocessing-Aware Services

When building a new service that creates or modifies historical data, follow this checklist to ensure it is fully compatible with the reprocessing engine.

  * **Data Model**: If you are creating a new table that stores historical, auditable data related to a `(portfolio_id, security_id)` key, it **must** have an `epoch` column.
  * **Unique Constraints**: Any unique constraints on your new table (e.g., `UNIQUE(portfolio_id, security_id, date)`) **must** be expanded to include the `epoch` (e.g., `UNIQUE(portfolio_id, security_id, date, epoch)`). This allows new and old versions of a record to coexist without violating database constraints.
  * **Consumers**: Any consumer in your service that processes versioned events **must** implement the `EpochFencer` pattern described above.
  * **Repositories**: Any repository method that queries for historical data (e.g., `get_snapshots_for_date_range`) **must** join with the `position_state` table and filter its results on `table.epoch = position_state.epoch`. This ensures that service logic and API queries only ever see data from the latest correct version of history.

<!-- end list -->

 