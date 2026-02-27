# RFC 058 - Generic Core Snapshot Contract for Stateful and Simulation Consumers

- Status: Proposed
- Date: 2026-02-27
- Authors: lotus-core and downstream service owners
- Related: RFC 035, RFC 036, RFC 043, RFC 046A, RFC 049, RFC 057, lotus-platform RFC-0067

## Problem Statement

Downstream services (including `lotus-risk`) need a deterministic, reusable, API-first data contract for:

1. Baseline portfolio state at a specific business date.
2. Projected state from simulation sessions.
3. Shared payload sections usable by multiple consumers (risk, performance, advisory, reporting).

Current lotus-core APIs provide many building blocks (`positions`, `simulation-sessions/*`) but require consumer-side orchestration and contract stitching that can drift over time.

## Goals

1. Define one generic configurable endpoint in lotus-core for baseline + simulation-aware portfolio snapshots.
2. Avoid concentration-specific or service-specific endpoint ownership in lotus-core.
3. Support multiple use cases through section controls and options.
4. Enforce canonical vocabulary and OpenAPI/inventory governance per RFC-0067.
5. Preserve strong API-first boundaries (no direct DB dependency for downstream apps).

## Non-Goals

1. Creating dedicated endpoint variants for individual consumers (for example concentration-only endpoint).
2. Implementing downstream analytics calculations in lotus-core.
3. Owning downstream service output schemas (risk/performance/reporting stay downstream-owned).

## Decision

lotus-core will expose one reusable integration endpoint:

- `POST /integration/portfolios/{portfolio_id}/core-snapshot`

The endpoint is section-driven, simulation-aware, and consumer-agnostic.

## Contract Requirements

### Request (normative)

```json
{
  "as_of_date": "2026-02-27",
  "reporting_currency": "USD",
  "sections": [
    "positions_baseline",
    "positions_projected",
    "portfolio_totals",
    "instrument_enrichment"
  ],
  "simulation": {
    "session_id": "SIM_0001"
  },
  "options": {
    "include_zero_quantity_positions": false,
    "include_cash_positions": true,
    "position_basis": "market_value_base"
  }
}
```

Required fields:

1. `portfolio_id` (path)
2. `as_of_date` (body)
3. `sections` (body; non-empty enum list)

Optional fields:

1. `reporting_currency`
 - if omitted, defaults to portfolio currency.
2. `simulation.session_id`
 - if supplied, projected sections are enabled.
3. `options.include_zero_quantity_positions` (default: `false`)
4. `options.include_cash_positions` (default: `true`)
5. `options.position_basis` (default: `market_value_base`)

### Response (normative)

```json
{
  "portfolio_id": "DEMO_DPM_EUR_001",
  "as_of_date": "2026-02-27",
  "reporting_currency": "USD",
  "portfolio_currency": "EUR",
  "simulation": {
    "session_id": "SIM_0001",
    "version": 3,
    "baseline_as_of_date": "2026-02-27"
  },
  "sections": {
    "positions_baseline": [
      {
        "security_id": "AAPL",
        "quantity": 100.0,
        "market_value_base": 19500.25,
        "market_value_local": 18000.0,
        "weight": 0.1245,
        "currency": "USD",
        "asset_class": "EQUITY",
        "sector": "TECHNOLOGY",
        "country_of_risk": "US"
      }
    ],
    "positions_projected": [
      {
        "security_id": "AAPL",
        "quantity": 120.0,
        "market_value_base": 23400.3,
        "market_value_local": 21600.0,
        "weight": 0.142,
        "currency": "USD",
        "asset_class": "EQUITY",
        "sector": "TECHNOLOGY",
        "country_of_risk": "US"
      }
    ],
    "portfolio_totals": {
      "total_market_value_base": 156600.4,
      "total_market_value_local": 145000.0
    }
  }
}
```

### Required section semantics

1. `positions_baseline`
 - point-in-time positions at `as_of_date`
 - includes deterministic basis fields:
   - `security_id`
   - `quantity`
   - `market_value_base` and/or basis selected by `options.position_basis`
   - `weight`
   - `currency`
2. `positions_projected`
 - projected state from simulation session for the same `as_of_date` context
 - same field semantics as baseline for direct comparability
3. `portfolio_totals`
 - totals required to validate/calibrate weights
4. `instrument_enrichment`
 - canonical enrichment attributes only (asset class, sector, country, etc.)

## Behavior Requirements

1. Baseline state must be resolved using explicit `as_of_date` (never implicit "today").
2. If `simulation.session_id` is present:
 - session must belong to requested `portfolio_id`
 - projected output must be generated from that session deterministically
 - response includes `simulation.version` and `simulation.baseline_as_of_date`
3. `reporting_currency` conversion must be deterministic and auditable.
4. If a requested section is unavailable, endpoint must fail explicitly (no silent partial drift).
5. Section ordering and field naming must remain stable and snake_case canonical.

## Error Contract Requirements

Use Lotus standard error envelope with `correlation_id`:

1. `400` invalid section/options values
2. `404` portfolio/session missing
3. `409` simulation session/portfolio mismatch
4. `422` schema validation failures
5. `default` unhandled service errors

## Governance and Inventory Requirements (RFC-0067)

Any implementation PR for this RFC must include:

1. OpenAPI updates with complete:
 - `summary`, `description`, tags
 - success + error responses
2. Schema property metadata:
 - every property has `description` and realistic `example`
3. Vocabulary inventory updates:
 - regenerate `api-vocabulary` artifact in same PR
 - no duplicate semantic attributes
 - no alias/camel-snake dual naming
 - no legacy terms where canonical terms exist
4. CI gates must pass:
 - OpenAPI quality gate
 - vocabulary inventory gate
 - no-alias/no-legacy-term guard
 - strict type checks

## Downstream Integration Requirements

This endpoint must support:

1. `lotus-risk` stateful and simulation concentration/risk workflows
2. `lotus-performance` stateful performance workflows
3. future advisory/reporting simulations without contract forks

Downstream services remain responsible for analytics calculations and output schemas.

## Implementation Plan

1. Contract-first PR:
 - DTOs for request/response with sections/options enums
 - OpenAPI docs/examples complete
2. Service orchestration PR:
 - baseline state assembly
 - simulation projection assembly
 - currency/weight normalization
3. Governance PR (can be combined):
 - vocabulary inventory regeneration
 - gate updates/tests
4. Integration validation PR:
 - consumer-facing smoke/integration tests using canonical fields

## Acceptance Criteria

1. `POST /integration/portfolios/{portfolio_id}/core-snapshot` returns deterministic baseline/projection sections for same inputs.
2. No concentration-specific endpoint is introduced in lotus-core.
3. Required sections and basis fields are available for `lotus-risk` concentration stateful/simulation flows.
4. RFC-0067 governance gates pass with updated inventory.
5. Contract is reusable for at least one non-risk consumer flow.
