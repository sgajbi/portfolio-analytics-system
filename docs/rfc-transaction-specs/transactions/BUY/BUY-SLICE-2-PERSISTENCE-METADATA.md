# BUY Slice 2 - Persistence Metadata Completion

## Scope

This slice implements the RFC-059 persistence traceability baseline for BUY metadata:

- `economic_event_id`
- `linked_transaction_group_id`
- `calculation_policy_id`
- `calculation_policy_version`
- `source_system`

## What Changed

- Extended `TransactionEvent` to carry the five metadata fields end-to-end.
- Extended `transactions` persistence model with matching columns.
- Added Alembic migration:
  - `alembic/versions/c1d2e3f4a5b6_feat_add_transaction_linkage_and_policy_metadata.py`
- Added persistence integration coverage for:
  - initial metadata write
  - idempotent UPSERT update semantics

## Validation Outcome

- Metadata is preserved when ingestion publishes transaction events.
- Persistence UPSERT keeps idempotent behavior while updating mutable metadata values.
- Existing transaction processing remains backward-compatible because new fields are optional.
