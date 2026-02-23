# RFC 038 - PAS Integration Capabilities API

## Status
Accepted

## Context
Platform RFCs require backend-driven configurability and explicit capability negotiation for BFF/PA/DPM consumers. PAS lacked a single discoverable API for feature/workflow capability metadata.

## Decision
Add `GET /integration/capabilities` in query-service.

Inputs:
- `consumerSystem` (BFF, PA, DPM, UI, UNKNOWN)
- `tenantId`

Output:
- contract and policy metadata
- supported input modes (`pas_ref`, `inline_bundle`)
- feature capability flags
- workflow capability flags

Configuration source:
- environment-backed flags (for now), designed to evolve into policy-pack/control-plane backed resolution.

## Rationale
1. Keeps feature/workflow control in backend services.
2. Enables BFF/UI to render from capabilities rather than hardcoded assumptions.
3. Supports PA/DPM dual-mode strategy (connected and stateless).

## Consequences
### Positive
- Explicit service-level integration contract for capability discovery.
- Cleaner separation of responsibilities between UI/BFF and domain services.

### Negative
- Requires ongoing governance to prevent uncontrolled feature-flag growth.
