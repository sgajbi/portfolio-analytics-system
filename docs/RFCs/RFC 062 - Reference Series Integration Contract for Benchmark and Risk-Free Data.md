# RFC 062 - Benchmark Reference Data and Assignment Contract for Downstream Analytics

## Status
Proposed

## Date
2026-03-01

## Owners
- lotus-core (assignment + reference data owner)
- lotus-performance (benchmark return/performance computation owner)
- lotus-risk (downstream analytics consumer via lotus-performance)

## 1. Problem Statement
Stateful analytics requires consistent benchmark context, but ownership must remain clean:

1. lotus-core is system-of-record for portfolio benchmark assignment and reference/master data.
2. lotus-performance is analytics owner and must compute benchmark daily returns/performance (single-index and composite).

Without an explicit core contract, downstream services risk drift in:
- benchmark assignment effective dating
- benchmark constituent/weight interpretation
- reference price/fx sourcing lineage
- reproducibility under restatements

## 2. Decision
Introduce lotus-core integration contracts for:

1. benchmark assignment resolution
2. benchmark reference data primitives needed by lotus-performance to compute benchmark returns
3. optional externally sourced benchmark/risk-free series passthrough (raw source only)

Normative boundary:
- lotus-core does not own derived benchmark return computation logic.
- lotus-performance computes and serves canonical benchmark return/performance outputs.

## 3. Scope
1. Portfolio-to-benchmark assignment resolution (effective dated).
2. Benchmark definition retrieval:
- single-index benchmark definition
- composite benchmark definition (components + weights + rebalance metadata)
3. Reference time series retrieval:
- index level prices/returns for component indices
- fx series for cross-currency normalization
- optional risk-free reference rates
4. Deterministic lineage metadata for downstream reproducibility.

## 4. Out of Scope
1. Benchmark return calculation and geometric linking in lotus-core.
2. Risk/performance/composite analytics in lotus-core.
3. Consumer-specific response shaping for lotus-risk/lotus-report.

## 5. Contract Requirements (Normative)

### 5.1 Benchmark Assignment
- Method: `POST`
- Path: `/integration/portfolios/{portfolio_id}/benchmark-assignment`
- Purpose: resolve benchmark identity for a portfolio context.

Request minimum:
- `as_of_date: date`
- `reporting_currency: str | None`
- `policy_context: {tenant_id, policy_pack_id} | None`

Response minimum:
- `portfolio_id`
- `as_of_date`
- `benchmark_id`
- `benchmark_name`
- `benchmark_type: SINGLE_INDEX | COMPOSITE`
- `benchmark_currency`
- `assignment_source`
- `effective_from`
- `effective_to`
- `contract_version`

### 5.2 Benchmark Definition
- Method: `POST`
- Path: `/integration/benchmarks/{benchmark_id}/definition`
- Purpose: return benchmark structure so lotus-performance can compute benchmark daily returns.

Request minimum:
- `as_of_date: date` (definition effective date)

Response minimum:
- `benchmark_id`
- `benchmark_type: SINGLE_INDEX|COMPOSITE`
- `base_currency`
- `components[]`:
  - `component_index_id`
  - `weight` (for composite)
  - `effective_from`
  - `effective_to`
- `rebalance_policy` (for composite)
- `metadata: {generated_at, correlation_id, source_version}`

### 5.3 Benchmark Component Market Series
- Method: `POST`
- Path: `/integration/benchmarks/{benchmark_id}/market-series`
- Purpose: return raw component series needed by lotus-performance for benchmark return construction.

Request minimum:
- `as_of_date: date`
- `window`
- `frequency`
- `target_currency: str | None`
- `series_fields: INDEX_PRICE | INDEX_RETURN | COMPONENT_WEIGHT | FX_RATE`

Response minimum:
- `benchmark_id`
- `component_series[]`:
  - `component_index_id`
  - `points[]: {date, index_price?, index_return?, component_weight?, fx_rate?}`
- `resolved_window`
- `diagnostics`
- `metadata`

### 5.4 Risk-Free Reference Series (Optional Upstream Source)
- Method: `POST`
- Path: `/integration/reference/risk-free-series`
- Purpose: return raw risk-free reference series for downstream conversion/computation.

Request minimum:
- `as_of_date: date`
- `window`
- `frequency`
- `currency`
- `series_mode: ANNUALIZED_RATE_SERIES|RETURN_SERIES`

Response minimum:
- `series_mode`
- `currency`
- `series[]: {date, value}`
- `resolved_window`
- `metadata`

## 6. Behavioral Requirements
1. Deterministic ordering and no duplicate dates.
2. Assignment and definition responses are effective-date deterministic.
3. Stable `source_version` and lineage metadata for reproducibility.
4. Cross-endpoint calendar consistency to avoid misaligned intersections downstream.
5. Correlation header propagation (`X-Correlation-Id`, request and response).

## 7. Precision and Data Semantics
1. Price/rate/weight values must be decimal-safe in transport contracts.
2. Reference series conventions must be explicit (price index, total return index, annualized rate).
3. Contract fields must never mix incompatible conventions silently.
4. Currency context must be explicit for every returned series block.

## 8. Error Contract
Platform-standard envelope with deterministic codes:
- `INVALID_REQUEST`
- `RESOURCE_NOT_FOUND`
- `INSUFFICIENT_DATA`
- `UNSUPPORTED_CONFIGURATION`
- `SOURCE_UNAVAILABLE`

## 9. RFC-0067 Governance
1. Full OpenAPI metadata completeness for operations and schema fields.
2. Canonical snake_case naming only.
3. API vocabulary inventory updates and conformance validation.
4. No alias and no legacy-term regressions.

## 10. Acceptance Criteria
1. Assignment and benchmark definition contracts are documented and implemented.
2. Market-series reference contract supports single-index and composite benchmark inputs.
3. Downstream lotus-performance benchmark return construction has no upstream contract gaps.
4. Contracts are deterministic and lineage-complete.
5. RFC-0067 and CI gates pass.

## 11. Downstream Mapping
This RFC is the upstream dependency for:
- lotus-performance benchmark return/performance construction (single-index + composite)
- lotus-performance `POST /integration/returns/series`
- lotus-risk stateful `POST /analytics/risk/calculate` (via lotus-performance)

It closes reference-data and assignment gaps while preserving service ownership boundaries:
- core owns assignment + reference data
- performance owns derived benchmark analytics
