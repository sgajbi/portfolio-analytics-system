# Enterprise Readiness Baseline (PAS)

- Standard reference: `lotus-platform/Enterprise Readiness Standard.md`
- Scope: core portfolio data query service, ingestion and reference-data aligned governance.
- Change control: RFC for cross-cutting policy updates; ADR for repo-level temporary exceptions.

## Security and IAM Baseline

- Write-path audit middleware is enabled for privileged mutation endpoints.
- Audit payload includes actor/tenant/role/correlation metadata with redaction.

Evidence:
- `src/services/query_service/app/enterprise_readiness.py`
- `src/services/query_service/app/main.py`
- `tests/unit/services/query_service/test_enterprise_readiness.py`

## API Governance Baseline

- Query service exposes versioned API contracts and OpenAPI metadata.
- Backward compatibility is managed by RFC process and contract tests.

Evidence:
- `src/services/query_service/app/main.py`
- `tests/integration/services/query_service`

## Configuration and Feature Management Baseline

- `ENTERPRISE_FEATURE_FLAGS_JSON` supports deterministic tenant/role feature controls.
- Invalid flag configuration results in safe deny-by-default behavior.

Evidence:
- `src/services/query_service/app/enterprise_readiness.py`
- `tests/unit/services/query_service/test_enterprise_readiness.py`

## Data Quality and Reconciliation Baseline

- Schema validation and data-quality guards are enforced at request and service boundaries.
- Reconciliation and durability controls are codified in dedicated standards.

Evidence:
- `docs/standards/durability-consistency.md`
- `docs/standards/scalability-availability.md`

## Reliability and Operations Baseline

- Health endpoints, resilience controls, migration gating, and runbook references are standardized.

Evidence:
- `src/services/query_service/app/main.py`
- `docs/standards/migration-contract.md`

## Privacy and Compliance Baseline

- Sensitive data redaction and audit context are mandatory for write-path logging.

Evidence:
- `src/services/query_service/app/enterprise_readiness.py`
- `tests/unit/services/query_service/test_enterprise_readiness.py`

## Deviations

- Deviations require ADR with mitigation plan and expiry review date.

