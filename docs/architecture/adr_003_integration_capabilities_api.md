# ADR 003 - Integration Capabilities API in PAS Query Service

- Status: Accepted
- Date: 2026-02-23

## Context

PAS must expose backend-driven capability metadata to support:
1. BFF/UI feature visibility and workflow control.
2. PA/DPM integration negotiation and dual input mode support.
3. Architectural rule that policy complexity remains in backend services.

## Decision

Implement `GET /integration/capabilities` in PAS query-service with:
1. consumer-aware capability resolution (`consumerSystem`)
2. tenant-aware context (`tenantId`)
3. policy/capability metadata response including supported input modes.

Initial implementation resolves feature flags from environment variables. This is an interim step until centralized policy-pack configuration is introduced.

## Consequences

### Positive
1. BFF/UI can consume explicit backend capability contracts.
2. Integration behavior is discoverable and testable.
3. Aligns PAS with platform RFCs for backend configurability.

### Negative
1. Environment-driven flag model is not yet centralized.
2. Requires future migration to shared policy/config service for multi-tenant scale.

## Links

1. `docs/RFCs/RFC 038 - PAS Integration Capabilities API.md`
2. `src/services/query_service/app/routers/capabilities.py`
