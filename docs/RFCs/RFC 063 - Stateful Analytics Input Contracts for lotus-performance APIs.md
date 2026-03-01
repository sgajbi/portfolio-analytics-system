# RFC 063 - Stateful Analytics Input Contracts for lotus-performance APIs

## Status
Proposed

## Date
2026-03-01

## Owners
- lotus-core (authoritative stateful data provider)
- lotus-performance (analytics computation owner)
- lotus-platform (contract governance)

## 1. Problem Statement
`lotus-performance` exposes analytics APIs (`/performance/twr`, `/performance/mwr`, `/performance/attribution`, `/contribution`, `/analytics/positions`, `/integration/returns/series`) that are fully computable in stateless mode today but not fully backed by stable lotus-core stateful input contracts.

Observed contract gaps on `lotus-core` `main`:
1. `POST /integration/portfolios/{portfolio_id}/performance-input` is not present.
2. `POST /portfolios/{portfolio_id}/positions-analytics` is not present.

As a result, stateful-mode enablement across all lotus-performance APIs is inconsistent and integration behavior is fragile.

## 2. Decision
Define and implement a dedicated stateful-input contract suite in lotus-core for lotus-performance analytics, while preserving ownership boundaries:
1. lotus-core owns canonical source data and integration input payloads.
2. lotus-performance owns all analytics calculations and response semantics.

## 3. Scope
This RFC defines required lotus-core query contracts and their required data points for:
1. TWR
2. MWR
3. Attribution
4. Contribution
5. Positions analytics feed
6. Returns-series feed (portfolio + benchmark + risk-free)

Out of scope:
1. Changes to lotus-performance formulas or scoring methodology.
2. UI/gateway response contracts.
3. Data ingestion mechanics (covered in ingestion RFCs).

## 4. API-to-Data Requirements Matrix

### 4.1 `lotus-performance` API: `POST /performance/twr` (stateful mode)
Required lotus-core endpoint:
1. `POST /integration/portfolios/{portfolio_id}/performance-input`

Required response data points:
1. `portfolio_id`
2. `performance_start_date`
3. `valuation_points[]` with each row containing:
   - `day`
   - `perf_date`
   - `begin_mv`
   - `bod_cf`
   - `eod_cf`
   - `mgmt_fees`
   - `end_mv`
4. `pas_contract_version`
5. `consumer_system`

### 4.2 `lotus-performance` API: `POST /performance/mwr` (stateful mode)
Required lotus-core endpoint:
1. `POST /integration/portfolios/{portfolio_id}/mwr-input`

Required response data points:
1. `portfolio_id`
2. `as_of_date`
3. `start_date`
4. `end_date`
5. `begin_mv`
6. `end_mv`
7. `cash_flows[]`:
   - `date`
   - `amount`
   - optional: `type` (`external_flow`, `fee`, `tax`, etc.)
8. `currency`
9. `contract_version`

### 4.3 `lotus-performance` API: `POST /performance/attribution` (stateful mode)
Required lotus-core endpoint:
1. `POST /integration/portfolios/{portfolio_id}/attribution-input`

Required response data points:
1. `portfolio_id`
2. `report_start_date`
3. `report_end_date`
4. `group_by_dimensions[]` (requested dimensions resolved)
5. `portfolio_data`:
   - `metric_basis`
   - `valuation_points[]` (`day`, `perf_date`, `begin_mv`, `bod_cf`, `eod_cf`, `mgmt_fees`, `end_mv`)
6. `instruments_data[]`:
   - `instrument_id`
   - `meta{}` (must contain all requested `group_by` dimensions)
   - `valuation_points[]` with same fields as portfolio
7. `benchmark_groups_data[]`:
   - `key{}` (dimension map)
   - `observations[]`:
     - `date`
     - `weight_bop`
     - `return_base`
     - optional: `return_local`
     - optional: `return_fx`
8. `currency_context`:
   - `portfolio_currency`
   - `reporting_currency`
9. `contract_version`

### 4.4 `lotus-performance` API: `POST /contribution` (stateful mode)
Required lotus-core endpoint:
1. `POST /integration/portfolios/{portfolio_id}/contribution-input`

Required response data points:
1. `portfolio_id`
2. `report_start_date`
3. `report_end_date`
4. `portfolio_data`:
   - `metric_basis`
   - `valuation_points[]` (`day`, `perf_date`, `begin_mv`, `bod_cf`, `eod_cf`, `mgmt_fees`, `end_mv`)
5. `positions_data[]`:
   - `position_id`
   - `meta{}`
   - `valuation_points[]` with same fields
6. optional hierarchy hints:
   - `supported_hierarchy_dimensions[]`
7. `currency_context`
8. `contract_version`

### 4.5 `lotus-performance` API: `POST /analytics/positions` (stateful mode)
Required lotus-core endpoint:
1. `POST /integration/portfolios/{portfolio_id}/positions-analytics-input`

Required response data points:
1. `portfolio_id`
2. `as_of_date`
3. `total_market_value`
4. `positions[]` (normalized row payload sufficient for lotus-performance passthrough and downstream consumers)
5. `contract_version`

### 4.6 `lotus-performance` API: `POST /integration/returns/series` (`core_api_ref`)
Required lotus-core endpoints:
1. `POST /integration/portfolios/{portfolio_id}/performance-input`
2. `POST /integration/portfolios/{portfolio_id}/benchmark-assignment` (already present)
3. `POST /integration/benchmarks/{benchmark_id}/return-series` (already present)
4. `POST /integration/reference/risk-free-series` (already present)

Required response data points:
1. Portfolio leg from `performance-input`:
   - `performance_start_date`
   - `valuation_points[]` (`day`, `perf_date`, `begin_mv`, `bod_cf`, `eod_cf`, `mgmt_fees`, `end_mv`)
2. Benchmark leg:
   - assignment: `benchmark_id`
   - series points: `series_date`, `benchmark_return`
3. Risk-free leg:
   - series points: `series_date`, `value`
   - `series_mode` (`return_series` or `annualized_rate_series`)
   - rate conventions (when applicable)

## 5. Contract Definitions (Normative)

### 5.1 `POST /integration/portfolios/{portfolio_id}/performance-input`
Request:
1. `as_of_date`
2. `lookback_days`
3. `consumer_system`

Response:
1. `portfolio_id`
2. `performance_start_date`
3. `valuation_points[]` with required daily valuation fields
4. `pas_contract_version`
5. `consumer_system`
6. `lineage`

### 5.2 `POST /integration/portfolios/{portfolio_id}/mwr-input`
Request:
1. `as_of_date`
2. `window` (`start_date`, `end_date`) or `period`
3. `consumer_system`

Response:
1. `portfolio_id`
2. `as_of_date`
3. `start_date`
4. `end_date`
5. `begin_mv`
6. `end_mv`
7. `cash_flows[]` (`date`, `amount`, optional `type`)
8. `currency`
9. `contract_version`
10. `lineage`

### 5.3 `POST /integration/portfolios/{portfolio_id}/attribution-input`
Request:
1. `report_start_date`
2. `report_end_date`
3. `group_by_dimensions[]`
4. `consumer_system`
5. optional `reporting_currency`

Response:
1. Full payload listed in section 4.3

### 5.4 `POST /integration/portfolios/{portfolio_id}/contribution-input`
Request:
1. `report_start_date`
2. `report_end_date`
3. optional `hierarchy[]`
4. `consumer_system`
5. optional `reporting_currency`

Response:
1. Full payload listed in section 4.4

### 5.5 `POST /integration/portfolios/{portfolio_id}/positions-analytics-input`
Request:
1. `as_of_date`
2. `sections[]`
3. optional `performance_periods[]`
4. `consumer_system`

Response:
1. Full payload listed in section 4.5

## 6. Error Contract
All endpoints in this RFC must use deterministic lotus-core integration error mapping:
1. `INVALID_REQUEST`
2. `RESOURCE_NOT_FOUND`
3. `INSUFFICIENT_DATA`
4. `SOURCE_UNAVAILABLE`
5. `CONTRACT_VIOLATION_UPSTREAM`
6. `UNSUPPORTED_CONFIGURATION`

## 7. Non-Functional Requirements
1. Deterministic ordering for all time-series arrays.
2. No duplicate dates per series.
3. Effective-dated determinism (same inputs and as-of context produce replay-equivalent payloads).
4. Correlation/request/trace propagation headers must be accepted and echoed.
5. OpenAPI + API vocabulary inventory compliance per RFC-0067.

## 8. Compatibility and Migration
1. Existing RFC-062 endpoints remain authoritative for benchmark/risk-free contracts.
2. `performance-input` and `positions-analytics-input` are required to unblock full stateful mode across all lotus-performance APIs.
3. lotus-performance will keep stateless request modes as fallback until all stateful contracts are available in production.

## 9. Test Requirements
1. Unit tests for all new request/response validators and policy branches.
2. Integration tests for each endpoint covering:
   - happy path
   - missing data
   - unsupported configuration
   - deterministic ordering and uniqueness
3. Contract smoke tests proving lotus-performance can run each stateful API path against lotus-core contracts.

## 10. Acceptance Criteria
1. All endpoints in section 5 are implemented in lotus-core query service.
2. `lotus-performance` runs stateful mode for TWR, MWR, attribution, contribution, positions, and returns-series without direct DB coupling.
3. RFC-0067 gates pass for lotus-core contract surfaces.
4. Cross-repo CI contract tests between lotus-core and lotus-performance are green.
