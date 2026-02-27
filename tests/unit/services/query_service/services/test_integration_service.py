import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import AsyncMock

from src.services.query_service.app.services.integration_service import IntegrationService


def make_service() -> IntegrationService:
    return IntegrationService(AsyncMock(spec=AsyncSession))


def test_canonical_consumer_system_mappings() -> None:
    service = make_service()
    assert service._canonical_consumer_system("DPM") == "lotus-manage"
    assert service._canonical_consumer_system("aea") == "lotus-gateway"
    assert service._canonical_consumer_system("UI") == "UI"
    assert service._canonical_consumer_system("Custom-System") == "custom-system"
    assert service._canonical_consumer_system(None) == "unknown"
    assert service._canonical_consumer_system("   ") == "unknown"


def test_load_policy_variants(monkeypatch: pytest.MonkeyPatch) -> None:
    service = make_service()

    monkeypatch.delenv("PAS_INTEGRATION_SNAPSHOT_POLICY_JSON", raising=False)
    assert service._load_policy() == {}

    monkeypatch.setenv("PAS_INTEGRATION_SNAPSHOT_POLICY_JSON", "not-json")
    assert service._load_policy() == {}

    monkeypatch.setenv("PAS_INTEGRATION_SNAPSHOT_POLICY_JSON", '["bad"]')
    assert service._load_policy() == {}

    monkeypatch.setenv(
        "PAS_INTEGRATION_SNAPSHOT_POLICY_JSON",
        '{"strictMode": true, "consumers": {"lotus-manage": ["OVERVIEW"]}}',
    )
    loaded = service._load_policy()
    assert loaded["strictMode"] is True
    assert "consumers" in loaded


def test_normalize_and_resolve_consumer_sections() -> None:
    service = make_service()
    assert service._normalize_sections(None) is None
    assert service._normalize_sections([" overview ", "HOLDINGS", "", 123]) == [
        "OVERVIEW",
        "HOLDINGS",
    ]

    sections, key = service._resolve_consumer_sections(None, "lotus-manage")
    assert sections is None
    assert key is None

    sections, key = service._resolve_consumer_sections(
        {"DPM": ["overview"], "other": ["x"]},
        "lotus-manage",
    )
    assert sections == ["OVERVIEW"]
    assert key == "DPM"

    sections, key = service._resolve_consumer_sections({"foo": ["x"]}, "lotus-manage")
    assert sections is None
    assert key is None


def test_resolve_policy_context_default(monkeypatch: pytest.MonkeyPatch) -> None:
    service = make_service()
    monkeypatch.delenv("PAS_INTEGRATION_SNAPSHOT_POLICY_JSON", raising=False)
    monkeypatch.delenv("PAS_POLICY_VERSION", raising=False)

    ctx = service._resolve_policy_context(tenant_id="default", consumer_system="lotus-manage")
    assert ctx.policy_version == "tenant-default-v1"
    assert ctx.policy_source == "default"
    assert ctx.matched_rule_id == "default"
    assert ctx.strict_mode is False
    assert ctx.allowed_sections is None
    assert "NO_ALLOWED_SECTION_RESTRICTION" in ctx.warnings


def test_resolve_policy_context_global_and_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    service = make_service()
    monkeypatch.setenv(
        "PAS_INTEGRATION_SNAPSHOT_POLICY_JSON",
        (
            '{"strictMode":false,'
            '"consumers":{"lotus-manage":["OVERVIEW","HOLDINGS"]},'
            '"tenants":{"tenant-a":{"strictMode":true,"consumers":{"DPM":["ALLOCATION"]}}}}'
        ),
    )
    monkeypatch.setenv("PAS_POLICY_VERSION", "tenant-v7")

    global_ctx = service._resolve_policy_context(
        tenant_id="default",
        consumer_system="lotus-manage",
    )
    assert global_ctx.policy_source == "global"
    assert global_ctx.matched_rule_id == "global.consumers.lotus-manage"
    assert global_ctx.strict_mode is False
    assert global_ctx.allowed_sections == ["OVERVIEW", "HOLDINGS"]

    tenant_ctx = service._resolve_policy_context(
        tenant_id="tenant-a",
        consumer_system="lotus-manage",
    )
    assert tenant_ctx.policy_version == "tenant-v7"
    assert tenant_ctx.policy_source == "tenant"
    assert tenant_ctx.matched_rule_id == "tenant.tenant-a.consumers.DPM"
    assert tenant_ctx.strict_mode is True
    assert tenant_ctx.allowed_sections == ["ALLOCATION"]


def test_resolve_policy_context_tenant_default_sections_and_strict_mode_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = make_service()
    monkeypatch.setenv(
        "PAS_INTEGRATION_SNAPSHOT_POLICY_JSON",
        (
            '{"tenants":{"tenant-x":{"strictMode":true,"defaultSections":["OVERVIEW"]},'
            '"tenant-y":{"strictMode":true}}}'
        ),
    )

    tenant_default_ctx = service._resolve_policy_context(
        tenant_id="tenant-x",
        consumer_system="lotus-manage",
    )
    assert tenant_default_ctx.policy_source == "tenant"
    assert tenant_default_ctx.matched_rule_id == "tenant.tenant-x.defaultSections"
    assert tenant_default_ctx.allowed_sections == ["OVERVIEW"]
    assert tenant_default_ctx.strict_mode is True

    strict_only_ctx = service._resolve_policy_context(
        tenant_id="tenant-y",
        consumer_system="lotus-manage",
    )
    assert strict_only_ctx.policy_source == "tenant"
    assert strict_only_ctx.matched_rule_id == "tenant.tenant-y.strictMode"
    assert strict_only_ctx.allowed_sections is None
    assert strict_only_ctx.strict_mode is True


def test_get_effective_policy_filters_requested_sections(monkeypatch: pytest.MonkeyPatch) -> None:
    service = make_service()
    monkeypatch.setenv(
        "PAS_INTEGRATION_SNAPSHOT_POLICY_JSON",
        '{"consumers":{"lotus-manage":["OVERVIEW","HOLDINGS"]}}',
    )

    response = service.get_effective_policy(
        consumer_system="DPM",
        tenant_id="default",
        include_sections=["overview", "allocation", "holdings"],
    )
    assert response.consumer_system == "lotus-manage"
    assert response.allowed_sections == ["OVERVIEW", "HOLDINGS"]
    assert response.policy_provenance.matched_rule_id == "global.consumers.lotus-manage"


def test_get_effective_policy_no_allowed_restriction_passthrough(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = make_service()
    monkeypatch.delenv("PAS_INTEGRATION_SNAPSHOT_POLICY_JSON", raising=False)

    response = service.get_effective_policy(
        consumer_system="custom-client",
        tenant_id="default",
        include_sections=["overview", "allocation"],
    )
    assert response.consumer_system == "custom-client"
    assert response.allowed_sections == ["OVERVIEW", "ALLOCATION"]
    assert "NO_ALLOWED_SECTION_RESTRICTION" in response.warnings

