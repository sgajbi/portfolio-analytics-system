# BUY Slice 4 - Lot, Cash Linkage, and Accrued-Offset State

## Scope Implemented

- Durable lot-state persistence for BUY transactions.
- Accrued-income offset initialization persistence for BUY transactions.
- Cashflow linkage metadata propagation (`economic_event_id`, `linked_transaction_group_id`).

## Storage Additions

- `position_lot_state`
  - one durable row per BUY transaction (`source_transaction_id` unique)
  - stores acquired/open quantity, lot cost local/base, and accrued-interest paid local
  - carries policy and linkage metadata
- `accrued_income_offset_state`
  - one durable row per BUY transaction (`source_transaction_id` unique)
  - initializes `remaining_offset_local` from BUY accrued interest
  - carries policy and linkage metadata
- `cashflows` extended with:
  - `economic_event_id`
  - `linked_transaction_group_id`

## Processing Integration

- Cost calculator BUY path now persists:
  - lot state
  - accrued offset state
- Cashflow calculator now propagates linkage metadata from transaction event into persisted cashflow records.

## Idempotency

- Lot and offset writes are implemented as UPSERTs keyed by `source_transaction_id`.
- Replays update deterministic state without creating duplicates.
