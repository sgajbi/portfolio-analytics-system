# RFC 063 - Lotus-Core Stateful Analytics Data Contracts (Delta-Only)

## Status
Proposed (Revised)

## Date
2026-03-01

## Owners
- lotus-core (canonical data provider)
- lotus-performance (analytics consumer)
- lotus-platform (contract governance)

## 1. Objective
Define the minimum lotus-core data contracts required for stateful analytics in lotus-performance.

This RFC is delta-only:
1. If a capability already exists and is compliant, no implementation change is required.
2. This RFC requests only missing or partially compliant capabilities.

## 2. Scope
In scope:
1. Portfolio valuation and cash-flow time series required for TWR and MWR.
2. Position valuation time series required for contribution and attribution.
3. Portfolio, instrument, and classification reference data required for grouping and decomposition.
4. Contract semantics, naming, quality, and error behavior.

Out of scope:
1. lotus-performance internal calculation logic.
2. Consumer endpoint design in lotus-performance.
3. New benchmark/risk-free contract design (covered by RFC-062).

## 3. Dependency Baseline
RFC-062 remains authoritative for benchmark and risk-free contracts.

Implication:
1. No new benchmark or risk-free contract is requested in RFC-063.
2. Only implementation quality/coverage gaps against RFC-062 should be addressed if discovered.

Terminology:
1. `as_of_date` is the request cutoff/context date.
2. `valuation_date` is the observation date for each returned time-series point.

## 4. Required Datasets and Canonical Fields

### 4.1 Portfolio Valuation and Cash-Flow Time Series
Purpose:
1. Single canonical input for both TWR and MWR.

Required request controls:
1. `portfolio_id`
2. `as_of_date`
3. window selector:
   - explicit: `start_date`, `end_date`
   - or relative-period selector
4. `reporting_currency` (optional but supported)
5. `consumer_system`

Required response metadata:
1. `portfolio_id`
2. `portfolio_currency`
3. `reporting_currency` (effective output currency)
4. `portfolio_open_date`
5. `portfolio_close_date` (nullable)
6. `performance_end_date` (nullable)
7. `contract_version`
8. `lineage`

Required time-series fields per observation:
1. `valuation_date`
2. `beginning_market_value`
3. `ending_market_value`
4. `cash_flows[]` with fields:
   - `amount`
   - `timing` (`bod` or `eod`)
   - `cash_flow_type` (for example `external_flow`, `fee`, `tax`, `transfer`)

Optional convenience fields (non-canonical aliases):
1. `beginning_of_day_cash_flow`
2. `end_of_day_cash_flow`
3. `management_fee_amount`

Rules:
1. Canonical representation is `cash_flows[]`; convenience fields are optional.
2. No separate valuation source should be required for MWR.

### 4.2 Position Valuation Time Series
Purpose:
1. Contribution and attribution inputs at instrument/group level.

Required request controls:
1. `portfolio_id`
2. `as_of_date`
3. window selector (`start_date`, `end_date`) when series output is requested
4. grouping selector (`sections`/`dimensions`)
5. `reporting_currency` (optional but supported)

Required response metadata:
1. `portfolio_id`
2. `portfolio_currency`
3. `reporting_currency`
4. `contract_version`
5. `lineage`

Required identifiers and dimensions:
1. `position_id`
2. `security_id`
3. grouping dimensions as supported by taxonomy (for example `asset_class`, `sector`, `region`, `country`)

Required valuation fields per observation:
1. `valuation_date`
2. `beginning_market_value_position_currency`
3. `ending_market_value_position_currency`
4. `beginning_market_value_portfolio_currency`
5. `ending_market_value_portfolio_currency`
6. `beginning_market_value_reporting_currency` (when reporting currency differs)
7. `ending_market_value_reporting_currency` (when reporting currency differs)

Optional valuation field per observation:
1. `cash_flows[]` using the same structure as portfolio-level cash flows

Optional fields:
1. `quantity` (optional; not required for base contribution math)
2. `issuer_id` (optional; required only for issuer-level analytics use cases)

### 4.3 Portfolio, Instrument, and Taxonomy Reference Data
Purpose:
1. Stable grouping, decomposition, and enrichment.

Required reference payloads:
1. Portfolio reference:
   - `portfolio_id`, `portfolio_currency`, `portfolio_open_date`, `portfolio_close_date`, mandate/category labels
2. Instrument reference:
   - `security_id`, display identifiers, trading currency
3. Classification taxonomy:
   - effective-dated canonical labels/dimensions used in grouping
4. Optional issuer hierarchy (only when requested):
   - `issuer_id`, `ultimate_parent_issuer_id`

### 4.4 Benchmark and Risk-Free Data
Requirement:
1. Use RFC-062 contracts as-is.
2. If integration tests expose a gap, fix the gap against RFC-062 semantics rather than adding new contract types here.

## 5. Delta Requests (Only If Missing)
Implement only missing or partially compliant items from section 4:
1. Lifecycle metadata completeness in portfolio time series.
2. Typed `cash_flows[]` completeness and cash-flow classification consistency.
3. Reporting-currency behavior and explicit output currency metadata.
4. Multi-currency valuation completeness in position time series.
5. Effective-dated taxonomy consistency for grouping dimensions.
6. Contract metadata completeness (`contract_version`, `lineage`).
7. RFC-062 benchmark/risk-free coverage and diagnostics quality gaps (if any).

## 6. Naming and Contract Standards
1. Canonical field names must be `snake_case`.
2. Currency context must be explicit in field names.
3. Canonical names must be self-explanatory; abbreviations are allowed only as optional compatibility aliases.
4. No alias-only definitions in canonical contracts.
5. OpenAPI and vocabulary assets must comply with RFC-0067.

## 7. Error Semantics
Contracts must map failures to stable error classes:
1. `INVALID_REQUEST`
2. `RESOURCE_NOT_FOUND`
3. `INSUFFICIENT_DATA`
4. `SOURCE_UNAVAILABLE`
5. `CONTRACT_VIOLATION_UPSTREAM`
6. `UNSUPPORTED_CONFIGURATION`

## 8. Non-Functional Requirements
1. Deterministic ordering for all time-series observations.
2. No duplicate `valuation_date` within a logical series key.
3. Logical series keys must be explicit:
   - portfolio series key: `portfolio_id` + `reporting_currency`
   - position series key: `portfolio_id` + `position_id` + `reporting_currency`
4. Effective-dated determinism for assignments and taxonomy.
5. Correlation/request/trace propagation in integration responses.

## 9. Acceptance Criteria
1. A gap assessment is documented for section 4 capabilities (`exists`, `partial`, `missing`).
2. Only `partial` and `missing` capabilities are implemented.
3. Portfolio time-series contract is sufficient for both TWR and MWR consumers.
4. Reporting-currency behavior is validated for portfolio and position datasets.
5. Lifecycle dates (`portfolio_open_date`, `portfolio_close_date`, `performance_end_date`) are populated and validated, including nullable handling for close/end dates.
6. Benchmark/risk-free integration remains RFC-062 compliant.
7. Cross-repo integration tests pass for stateful analytics readiness.
