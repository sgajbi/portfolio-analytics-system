# RFC 056 - Remove Legacy Query Analytics and Reporting Endpoints

## Problem Statement
PAS query-service still exposes deprecated advanced analytics and reporting-style endpoints that are no longer aligned to target service ownership:
- advanced analytics belongs to PA
- reporting/aggregation belongs to RAS

## Root Cause
- Endpoints were marked `deprecated` but kept active to ease transition.
- Runtime behavior still executes local PAS analytics/reporting logic for these routes.

## Proposed Solution
Hard-disable legacy PAS query-service endpoints by returning `410 Gone` with explicit migration targets:
- `POST /portfolios/{portfolio_id}/performance` -> PA
- `POST /portfolios/{portfolio_id}/performance/mwr` -> PA
- `POST /portfolios/{portfolio_id}/risk` -> PA
- `POST /portfolios/{portfolio_id}/concentration` -> PA
- `POST /portfolios/{portfolio_id}/summary` -> RAS
- `POST /portfolios/{portfolio_id}/review` -> RAS

## Architectural Impact
- Enforces service boundaries at runtime, not only in documentation.
- Prevents duplicate analytics/reporting logic drift in PAS.
- Strengthens API-driven integration toward PA and RAS.

## Risks and Trade-offs
- Existing internal tests or scripts calling these routes must migrate immediately.
- Temporary disruption for local consumers not yet switched to PA/RAS.

Mitigations:
- Clear `410` error messages with target endpoints.
- Contract/integration test updates in this RFC scope.

## High-Level Implementation Approach
1. Update affected routers to return deterministic `410 Gone` responses.
2. Keep route surfaces temporarily for explicit migration signaling.
3. Update integration/e2e tests to assert `410` behavior.
4. Update runbook/docs to point to PA/RAS authoritative routes.

## Success Criteria
- Legacy PAS analytics/reporting routes no longer perform calculations.
- All affected tests and docs align to migration messaging.
- PAS runtime only serves core data and integration contracts.
