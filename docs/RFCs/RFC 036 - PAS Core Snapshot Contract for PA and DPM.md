# RFC 036 - PAS Core Snapshot Contract for PA and DPM

- Date: 2026-02-23
- Services Affected: `query-service`, `performanceAnalytics`, `dpm-rebalance-engine`, BFF
- Status: Implemented (v1)

## Summary

Introduces a versioned PAS integration contract endpoint that provides a canonical as-of snapshot for PA/DPM consumption.

## Endpoint

- `POST /integration/portfolios/{portfolio_id}/core-snapshot`

## Contract Properties

1. `contractVersion` for schema versioning.
2. `asOfDate` control in request payload.
3. `includeSections` to choose payload breadth per consumer use case.
4. `consumerSystem` field for integration traceability.

## Response Composition

1. Canonical PAS portfolio record.
2. As-of snapshot assembled by PAS review orchestration.

## Why This Matters

1. Gives PA and DPM a stable PAS-owned boundary.
2. Reduces duplicate data-access logic in downstream systems.
3. Enables controlled evolution via explicit versioning.

## Next Steps

1. Completed via `RFC 043 - PAS Core Snapshot Contract Hardening (Freshness, Lineage, Section Governance)`:
   - explicit provenance/freshness metadata,
   - policy-driven section governance controls.
2. Continue BFF-level adapters to map PAS contract into UI-specific view models.
