# BUY Slice 5 - Query Surfaces and Lifecycle Observability

## Scope Implemented

- Added BUY lot query API surface.
- Added BUY accrued-income offset query API surface.
- Added BUY cash-linkage query API surface.
- Added BUY lifecycle stage metrics and structured lifecycle logs in the cost-calculator flow.

## New Query APIs

- `GET /portfolios/{portfolio_id}/positions/{security_id}/lots`
- `GET /portfolios/{portfolio_id}/positions/{security_id}/accrued-offsets`
- `GET /portfolios/{portfolio_id}/transactions/{transaction_id}/cash-linkage`

These endpoints expose durable state produced by Slice 4 and support supportability/reconciliation use cases.

## Observability Additions

- Prometheus counter:
  - `buy_lifecycle_stage_total{stage,status}`
- Stage instrumentation in cost calculator for:
  - transaction cost persistence
  - lot-state persistence
  - accrued-offset-state persistence
  - outbox emission
- Structured `buy_state_persisted` log event with linkage/policy metadata.

## Governance

- OpenAPI quality gate passed.
- API vocabulary inventory regenerated for `lotus-core`.
- Platform catalog sync + cross-app validator passed in `lotus-platform`.
