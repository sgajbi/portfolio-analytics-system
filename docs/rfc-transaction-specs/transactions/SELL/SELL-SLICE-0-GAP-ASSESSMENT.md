# SELL Slice 0 Gap Assessment

## Scope

This assessment captures the baseline gap between current `lotus-core` SELL behavior and `RFC-SELL-01` before functional SELL implementation changes.

Status labels:

- `COVERED`
- `PARTIALLY_COVERED`
- `NOT_COVERED`

Behavior labels:

- `MATCHES`
- `PARTIALLY_MATCHES`
- `DOES_NOT_MATCH`

## Requirement Matrix

| Requirement | Implementation Status | Behavior Match | Current Observed Behavior | Target Behavior | Risk if Unchanged | Proposed Action | Blocking |
|---|---|---|---|---|---|---|---|
| Lifecycle stage order (receive -> validate -> normalize -> policy -> calculate -> effects -> persist -> publish -> observability) | PARTIALLY_COVERED | PARTIALLY_MATCHES | Core stages exist across ingestion, persistence, and calculators but are not represented as explicit, queryable stage state per SELL. | Deterministic, diagnosable lifecycle stage model for every SELL. | Incident triage and reconciliation remain slower and less deterministic. | Add stage-state persistence and support visibility in Slice 5. | Yes |
| SELL semantic invariant: reduces quantity/exposure | COVERED | MATCHES | Position calculator reduces quantity for `SELL` and `TRANSFER_OUT`. | Same behavior with explicit SELL invariants. | Regression risk during canonical refactor if not locked. | Keep under characterization; enforce explicit invariants in Slice 3. | Yes |
| SELL cost basis disposal and realized P&L calculation | COVERED | PARTIALLY_MATCHES | Cost engine computes disposal and realized gain/loss; decomposition and policy-trace semantics are not yet explicit at canonical contract level. | Canonical deterministic disposal + realized capital/FX/total decomposition with policy traceability. | Accounting transparency gaps under audit/replay scenarios. | Harden in Slices 2-3. | Yes |
| Canonical linkage (`economic_event_id`, `linked_transaction_group_id`) | PARTIALLY_COVERED | PARTIALLY_MATCHES | Linkage infrastructure exists in core transaction metadata, but SELL disposal/cash reconciliation linkage is not yet complete end-to-end per RFC surface. | SELL effects and linked cash are fully reconcilable by stable linkage ids. | Cash/security reconciliation ambiguity for support and audit. | Complete linkage semantics in Slices 2 and 4. | Yes |
| Lot disposal traceability (per-lot effects and disposal method) | PARTIALLY_COVERED | PARTIALLY_MATCHES | Disposal strategy exists in cost engine but explicit canonical disposal state/query contract is incomplete. | Deterministic lot-disposal evidence and method visibility for each SELL. | Harder post-trade audit and tax-lot explainability. | Implement disposal persistence/query surfaces in Slices 3-5. | Yes |
| Oversell/short policy behavior | PARTIALLY_COVERED | PARTIALLY_MATCHES | Engine-side insufficient quantity handling exists, but RFC-level deterministic policy matrix and reason-code surface are incomplete. | Policy-driven oversell behavior with deterministic reason codes. | Inconsistent behavior under edge cases and weak support diagnostics. | Define policy matrix and reason codes in Slice 1; enforce in Slice 4. | Yes |
| Accrued-interest received separation for fixed-income SELL | NOT_COVERED | DOES_NOT_MATCH | SELL handling does not yet expose canonical accrued-interest-received separation and reporting shape required by RFC. | Accrued-interest received separated from capital P&L and queryable for fixed income flows. | Misclassification risk in income/capital analytics and reporting. | Add in Slices 3-5. | Yes |
| Failure reason taxonomy with deterministic reason codes | PARTIALLY_COVERED | PARTIALLY_MATCHES | Existing validation/runtime failures exist but SELL-specific deterministic reason-code taxonomy is not complete. | Canonical SELL reason-code catalog for validation and processing failures. | Inconsistent QA/support handling. | Introduce in Slice 1. | Yes |
| Query surfaces: SELL disposal + realized breakdown + linkage + policy trace | PARTIALLY_COVERED | PARTIALLY_MATCHES | Baseline transaction query exposes realized fields and core metadata; disposal-level and full lifecycle/audit surfaces are incomplete. | Full canonical SELL query visibility and support payloads. | Downstream consumers cannot rely on complete canonical surface. | Extend in Slice 5. | Yes |
| Idempotency/replay safety for SELL side effects | COVERED | PARTIALLY_MATCHES | Core idempotency/replay protections exist platform-wide, but SELL-specific disposal/linkage invariants are not fully asserted. | Replay-safe canonical SELL with deterministic disposal and linkage effects. | Duplicate/disputed disposal outcomes under advanced recovery flows. | Expand SELL replay coverage in Slices 2-4. | Yes |
| Observability diagnosability per SELL lifecycle stage | PARTIALLY_COVERED | PARTIALLY_MATCHES | Structured logs and metrics exist at service level; lifecycle stage observability for SELL is not yet exposed as first-class state. | Stage-aware SELL observability and support diagnostics payloads. | Slow root-cause analysis in production incidents. | Complete in Slice 5. | No |

## Characterization Coverage Added in Slice 0

- SELL ingestion DTO baseline behavior lock (`trade_fee` defaulting).
- SELL fee transformation lock from ingestion event to cost engine payload.
- SELL position quantity/cost-basis baseline progression lock using current `net_cost` semantics.
- SELL query record mapping lock for transaction-level realized/net-cost fields.

### Important transition rule

Slice 0 characterization locks current behavior only for refactoring safety.
As implementation slices progress, these tests must be promoted to canonical assertions aligned to `RFC-SELL-01` final semantics.
No legacy assertion should remain if it conflicts with approved RFC behavior.

## Notes

- This assessment records current behavior; it does not modify SELL logic.
- Functional conformance to `RFC-SELL-01` begins in Slice 1 onward.
