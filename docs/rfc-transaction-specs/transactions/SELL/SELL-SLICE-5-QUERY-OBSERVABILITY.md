# SELL Slice 5 - Query Surfaces and Lifecycle Observability

## Scope Implemented

- Added SELL disposal query API surface.
- Added SELL cash-linkage query API surface.
- Added SELL lifecycle stage metrics and structured lifecycle logs in the cost-calculator flow.

## New Query APIs

- `GET /portfolios/{portfolio_id}/positions/{security_id}/sell-disposals`
- `GET /portfolios/{portfolio_id}/transactions/{transaction_id}/sell-cash-linkage`

These endpoints expose deterministic SELL state needed for audit, reconciliation, and operational support.

## Observability Additions

- Prometheus counter:
  - `sell_lifecycle_stage_total{stage,status}`
- Stage instrumentation in cost calculator for SELL:
  - transaction cost persistence
  - outbox emission
  - retryable/failed process outcomes
- Structured `sell_state_persisted` log event with linkage/policy metadata.

## Governance

- OpenAPI quality gate passed.
- API vocabulary inventory regenerated for `lotus-core`.
- Platform catalog sync + cross-app validator passed in `lotus-platform`.
