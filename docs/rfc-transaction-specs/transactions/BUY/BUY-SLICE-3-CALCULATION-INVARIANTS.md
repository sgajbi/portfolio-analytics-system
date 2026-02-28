# BUY Slice 3 - Calculation and Invariant Hardening

## Scope Implemented

- Canonical BUY calculation hardening in the financial calculation engine.
- Deterministic BUY invariant checks.
- Explicit realized P&L zero emission for BUY events.
- Policy hook for accrued-interest exclusion from BUY book cost.

## Behavior Changes

- BUY now emits:
  - `realized_gain_loss = 0`
  - `realized_gain_loss_local = 0`
- BUY principal `gross_cost` now follows base-currency semantics:
  - `gross_cost = gross_transaction_amount * transaction_fx_rate`
- Invariant failures are captured with deterministic reason text:
  - quantity must be positive
  - gross/base/book costs must be non-negative
  - realized P&L for BUY must remain explicit zero

## Policy Hook Added

- `calculation_policy_id = BUY_EXCLUDE_ACCRUED_INTEREST_FROM_BOOK_COST`
  - excludes accrued interest from BUY book cost while keeping principal and fees in cost basis.

## Tests Added/Updated

- Financial engine unit tests:
  - BUY explicit zero realized P&L
  - cross-currency BUY gross/base cost consistency
  - accrued-interest exclusion policy behavior
  - quantity invariant violation behavior
- Cost calculator consumer unit test:
  - verifies BUY emits explicit zero realized P&L values
- Transaction processor unit test:
  - verifies BUY transactions in recalculation timeline carry zero realized P&L
