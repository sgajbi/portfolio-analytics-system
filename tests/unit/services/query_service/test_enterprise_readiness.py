import json

from src.services.query_service.app.enterprise_readiness import (
    authorize_write_request,
    is_feature_enabled,
    redact_sensitive,
    validate_enterprise_runtime_config,
)


def test_feature_flags_tenant_role_resolution(monkeypatch):
    monkeypatch.setenv(
        "ENTERPRISE_FEATURE_FLAGS_JSON",
        json.dumps(
            {
                "query.advanced": {
                    "tenant-1": {"analyst": True, "*": False},
                    "*": {"*": False},
                }
            }
        ),
    )
    assert is_feature_enabled("query.advanced", "tenant-1", "analyst") is True
    assert is_feature_enabled("query.advanced", "tenant-1", "viewer") is False


def test_redaction_masks_sensitive_keys():
    payload = {"authorization": "Bearer abc", "nested": {"account_number": "1234", "ok": 1}}
    redacted = redact_sensitive(payload)
    assert redacted["authorization"] == "***REDACTED***"
    assert redacted["nested"]["account_number"] == "***REDACTED***"
    assert redacted["nested"]["ok"] == 1


def test_authorize_write_request_enforces_required_headers_when_enabled(monkeypatch):
    monkeypatch.setenv("ENTERPRISE_ENFORCE_AUTHZ", "true")
    allowed, reason = authorize_write_request("POST", "/transactions", {})
    assert allowed is False
    assert reason.startswith("missing_headers:")


def test_authorize_write_request_enforces_capability_rules(monkeypatch):
    monkeypatch.setenv("ENTERPRISE_ENFORCE_AUTHZ", "true")
    monkeypatch.setenv(
        "ENTERPRISE_CAPABILITY_RULES_JSON",
        json.dumps({"POST /transactions": "transactions.write"}),
    )
    headers = {
        "X-Actor-Id": "a1",
        "X-Tenant-Id": "t1",
        "X-Role": "ops",
        "X-Correlation-Id": "c1",
        "X-Service-Identity": "pas",
        "X-Capabilities": "transactions.read",
    }
    denied, denied_reason = authorize_write_request("POST", "/transactions/import", headers)
    assert denied is False
    assert denied_reason == "missing_capability:transactions.write"

    headers["X-Capabilities"] = "transactions.read,transactions.write"
    allowed, allowed_reason = authorize_write_request("POST", "/transactions/import", headers)
    assert allowed is True
    assert allowed_reason is None


def test_validate_enterprise_runtime_config_reports_rotation_issue(monkeypatch):
    monkeypatch.setenv("ENTERPRISE_SECRET_ROTATION_DAYS", "120")
    issues = validate_enterprise_runtime_config()
    assert "secret_rotation_days_out_of_range" in issues
