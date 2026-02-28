# BUY Slice 0 Gap Assessment

## Scope

This assessment captures the baseline gap between current `lotus-core` BUY behavior and `RFC-BUY-01` before any functional implementation changes.

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
| Lifecycle stage order (receive -> validate -> normalize -> policy -> calculate -> effects -> persist -> publish -> observability) | PARTIALLY_COVERED | PARTIALLY_MATCHES | Stages exist across services but are distributed and not explicitly persisted per transaction as stage state. | Deterministic stage model with diagnosable stage status. | Low diagnosability during incidents and reconciliation. | Add lifecycle status model and stage telemetry in later slices. | Yes |
| BUY semantic invariant: increases quantity/exposure | COVERED | MATCHES | Position calculator increases quantity for BUY. | Same. | Regression risk if refactor occurs. | Keep behavior under characterization tests. | Yes |
| BUY must create cost basis | COVERED | PARTIALLY_MATCHES | Cost basis is updated using current `net_cost` pipeline. | Canonical cost behavior with policy-linked derivation and invariants. | Accounting drift for unhandled policy combinations. | Harden in Slice 3 with canonical calculations. | Yes |
| BUY must not realize P&L at booking | PARTIALLY_COVERED | PARTIALLY_MATCHES | Engine/consumer path generally emits no realized gain for BUY, but explicit canonical invariant enforcement is missing. | Explicit zero realized capital/FX/total P&L local/base. | Silent drift possible if engine behavior changes. | Add invariant checks + explicit fields in Slice 3. | Yes |
| Canonical linkage (`economic_event_id`, `linked_transaction_group_id`) | NOT_COVERED | DOES_NOT_MATCH | No canonical linkage ids persisted for BUY. | Stable linkage ids persisted and queryable. | Cash/security reconciliation gaps. | Add schema + generation rules in Slice 2. | Yes |
| Lot creation/update for BUY | NOT_COVERED | DOES_NOT_MATCH | No dedicated lot-state model in core schema. | BUY creates auditable acquisition lots. | Disposal and tax-lot accuracy constraints for future RFCs. | Implement lot state in Slice 4. | Yes |
| Accrued-interest offset initialization (fixed income BUY) | NOT_COVERED | DOES_NOT_MATCH | No persisted accrued-income-offset model tied to BUY. | Offset initialized, stored, and consumable by future income events. | Incorrect income treatment for fixed-income flows. | Implement offset state and tests in Slice 4. | Yes |
| Policy id/version traceability | NOT_COVERED | DOES_NOT_MATCH | Policy influence exists but transaction-level policy id/version persistence is absent. | Every BUY stores active policy id/version. | Poor auditability and reproducibility. | Add policy metadata in Slice 2. | Yes |
| Failure reason taxonomy with deterministic reason codes | PARTIALLY_COVERED | PARTIALLY_MATCHES | Validation/runtime errors exist, but canonical reason-code taxonomy is incomplete. | Deterministic reason-code catalog for BUY validation and processing errors. | Inconsistent support and QA handling. | Introduce BUY reason codes in Slice 1. | Yes |
| Query surfaces: enriched BUY + lot + linkage + offset | PARTIALLY_COVERED | PARTIALLY_MATCHES | Enriched transaction and related cashflow are queryable; lot/offset/linkage views are missing. | Full required surfaces available and consistent. | Incomplete downstream integration surface. | Extend query in Slice 5 after state models exist. | Yes |
| Idempotency/replay safety | COVERED | PARTIALLY_MATCHES | Core idempotency and replay support exists in services; BUY-specific invariants are not fully guarded. | Replay-safe canonical BUY with linkage/cash dedupe protections. | Duplicate side effects under advanced flows. | Expand BUY replay tests in Slices 2-4. | Yes |
| Observability diagnosability per lifecycle stage | PARTIALLY_COVERED | PARTIALLY_MATCHES | Structured logs exist, but no consistent stage-state exposure per transaction. | Stage-aware observability and support payloads. | Slow incident triage. | Complete in Slice 5. | No |

## Characterization Coverage Added in Slice 0

- BUY ingestion DTO baseline behavior lock.
- BUY fee-to-engine transformation behavior lock.
- BUY position quantity/cost basis progression lock.
- BUY query response mapping lock for transaction-level fields.

### Important transition rule

Slice 0 characterization locks current behavior only for refactoring safety.
As implementation slices progress, these tests must be promoted to canonical assertions that match `RFC-BUY-01` final semantics.
No legacy assertion should remain if it conflicts with approved RFC behavior.

## Notes

- This assessment intentionally captures current behavior without altering it.
- Functional conformance to `RFC-BUY-01` begins in Slice 1 onward.
