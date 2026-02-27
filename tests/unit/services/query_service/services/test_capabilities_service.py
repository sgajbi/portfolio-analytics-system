from src.services.query_service.app.services.capabilities_service import CapabilitiesService


def test_capabilities_default_flags(monkeypatch):
    monkeypatch.delenv("LOTUS_CORE_INGEST_UPLOAD_APIS_ENABLED", raising=False)
    monkeypatch.delenv("LOTUS_CORE_INGEST_PORTFOLIO_BUNDLE_ENABLED", raising=False)
    monkeypatch.delenv("LOTUS_CORE_POLICY_VERSION", raising=False)
    monkeypatch.delenv("LOTUS_CORE_CAPABILITY_TENANT_OVERRIDES_JSON", raising=False)

    service = CapabilitiesService()
    response = service.get_integration_capabilities(
        consumer_system="lotus-gateway", tenant_id="default"
    )

    assert response.contract_version == "v1"
    assert response.consumer_system == "lotus-gateway"
    assert response.policy_version == "tenant-default-v1"
    assert set(response.supported_input_modes) == {
        "lotus_core_ref",
        "inline_bundle",
        "file_upload",
    }
    assert all(feature.enabled for feature in response.features[:2])


def test_capabilities_env_override(monkeypatch):
    monkeypatch.setenv("LOTUS_CORE_INGEST_UPLOAD_APIS_ENABLED", "false")
    monkeypatch.setenv("LOTUS_CORE_INGEST_PORTFOLIO_BUNDLE_ENABLED", "false")
    monkeypatch.setenv("LOTUS_CORE_POLICY_VERSION", "tenant-x-v3")
    monkeypatch.delenv("LOTUS_CORE_CAPABILITY_TENANT_OVERRIDES_JSON", raising=False)

    service = CapabilitiesService()
    response = service.get_integration_capabilities(
        consumer_system="lotus-manage", tenant_id="tenant-x"
    )

    feature_map = {feature.key: feature.enabled for feature in response.features}
    assert feature_map["lotus_core.ingestion.bulk_upload_adapter"] is False
    assert feature_map["lotus_core.ingestion.portfolio_bundle_adapter"] is False
    assert response.policy_version == "tenant-x-v3"
    assert set(response.supported_input_modes) == {"lotus_core_ref"}
    assert response.tenant_id == "tenant-x"


def test_capabilities_tenant_policy_override(monkeypatch):
    monkeypatch.setenv(
        "LOTUS_CORE_CAPABILITY_TENANT_OVERRIDES_JSON",
        (
            '{"tenant-a":{"policy_version":"tenant-a-v7",'
            '"features":{"lotus_core.ingestion.bulk_upload_adapter":false,'
            '"lotus_core.ingestion.portfolio_bundle_adapter":false,'
            '"lotus_core.support.lineage_api":false},'
            '"workflows":{"portfolio_bulk_onboarding":false},'
            '"supported_input_modes":{"lotus-manage":["lotus_core_ref"],"default":["lotus_core_ref"]}}}'
        ),
    )
    monkeypatch.setenv("LOTUS_CORE_INGEST_UPLOAD_APIS_ENABLED", "true")
    monkeypatch.setenv("LOTUS_CORE_INGEST_PORTFOLIO_BUNDLE_ENABLED", "true")

    service = CapabilitiesService()
    response = service.get_integration_capabilities(
        consumer_system="lotus-manage", tenant_id="tenant-a"
    )
    feature_map = {feature.key: feature.enabled for feature in response.features}
    workflow_map = {workflow.workflow_key: workflow.enabled for workflow in response.workflows}

    assert response.policy_version == "tenant-a-v7"
    assert response.supported_input_modes == ["lotus_core_ref"]
    assert feature_map["lotus_core.ingestion.bulk_upload_adapter"] is False
    assert feature_map["lotus_core.ingestion.portfolio_bundle_adapter"] is False
    assert feature_map["lotus_core.support.lineage_api"] is False
    assert workflow_map["portfolio_bulk_onboarding"] is False


def test_capabilities_ignores_invalid_tenant_policy_json(monkeypatch):
    monkeypatch.setenv("LOTUS_CORE_CAPABILITY_TENANT_OVERRIDES_JSON", "not-json")

    service = CapabilitiesService()
    response = service.get_integration_capabilities(
        consumer_system="lotus-gateway", tenant_id="tenant-a"
    )

    assert response.policy_version == "tenant-default-v1"
    assert set(response.supported_input_modes) == {
        "lotus_core_ref",
        "inline_bundle",
        "file_upload",
    }


def test_capabilities_ignores_non_object_overrides_payload(monkeypatch):
    monkeypatch.setenv("LOTUS_CORE_CAPABILITY_TENANT_OVERRIDES_JSON", '["invalid"]')
    service = CapabilitiesService()

    response = service.get_integration_capabilities(
        consumer_system="lotus-manage", tenant_id="tenant-a"
    )

    assert response.policy_version == "tenant-default-v1"
    assert response.supported_input_modes == ["lotus_core_ref"]


def test_capabilities_ignores_invalid_tenant_entries_and_non_dict_workflow_override(monkeypatch):
    monkeypatch.setenv(
        "LOTUS_CORE_CAPABILITY_TENANT_OVERRIDES_JSON",
        ('{"tenant-x":{"workflows":["invalid"],"policy_version":"tenant-x-v1"},"tenant-y":"bad"}'),
    )
    service = CapabilitiesService()
    response = service.get_integration_capabilities(
        consumer_system="lotus-manage", tenant_id="tenant-x"
    )

    workflow_map = {workflow.workflow_key: workflow.enabled for workflow in response.workflows}
    assert response.policy_version == "tenant-x-v1"
    assert workflow_map["portfolio_bulk_onboarding"] is True
