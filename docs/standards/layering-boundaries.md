# Layering and Boundary Rules

This standard defines guardrails for directory organization and dependency boundaries in `lotus-core`.

## Rules

1. Service entrypoints must stay thin.
 - No heavy business logic in `app/main.py`, router modules, or worker bootstraps.
2. Domain logic must be transport-agnostic.
 - Domain code cannot depend on FastAPI, Kafka clients, or SQLAlchemy sessions.
3. Adapter code must not become a second domain layer.
 - Adapters translate IO/protocols and delegate to application/domain logic.
4. API contracts are canonical integration boundaries.
 - No downstream direct DB access contract.
5. Removed ownership domains must not re-enter lotus-core.
 - Risk/performance/concentration/reporting orchestration logic is out of scope.
6. Position-level core metrics must converge on canonical positions resources.
 - Avoid parallel position contracts with overlapping semantics.

## Enforcement Approach

1. Documentation and RFC gate:
 - Architecture and ownership changes require RFC updates.
2. Static checks:
 - Use script-based guard checks for known boundary violations.
3. CI conformance:
 - OpenAPI, vocabulary, no-alias, and migration checks remain mandatory.

## Transitional Policy

During RFC 057 rollout:

1. Structural refactors are performed in small PRs with behavior lock tests.
2. Transitional endpoints are removed when approved in RFC 057 decisions.
3. Downstream migrations are tracked in downstream repositories; lotus-core does not retain legacy ownership APIs.
