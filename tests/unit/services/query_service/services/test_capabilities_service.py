from src.services.query_service.app.services.capabilities_service import CapabilitiesService


def test_capabilities_default_flags(monkeypatch):
    monkeypatch.delenv("PAS_CAP_CORE_SNAPSHOT_ENABLED", raising=False)
    monkeypatch.delenv("PAS_CAP_UPLOAD_APIS_ENABLED", raising=False)
    monkeypatch.delenv("PAS_POLICY_VERSION", raising=False)
    monkeypatch.delenv("PAS_CAPABILITY_TENANT_OVERRIDES_JSON", raising=False)

    service = CapabilitiesService()
    response = service.get_integration_capabilities(consumer_system="BFF", tenant_id="default")

    assert response.contract_version == "v1"
    assert response.consumer_system == "BFF"
    assert response.policy_version == "tenant-default-v1"
    assert "pas_ref" in response.supported_input_modes
    assert all(feature.enabled for feature in response.features[:2])


def test_capabilities_env_override(monkeypatch):
    monkeypatch.setenv("PAS_CAP_UPLOAD_APIS_ENABLED", "false")
    monkeypatch.setenv("PAS_POLICY_VERSION", "tenant-x-v3")
    monkeypatch.delenv("PAS_CAPABILITY_TENANT_OVERRIDES_JSON", raising=False)

    service = CapabilitiesService()
    response = service.get_integration_capabilities(consumer_system="PA", tenant_id="tenant-x")

    feature_map = {feature.key: feature.enabled for feature in response.features}
    assert feature_map["pas.ingestion.bulk_upload"] is False
    assert response.policy_version == "tenant-x-v3"
    assert set(response.supported_input_modes) == {"pas_ref", "inline_bundle"}
    assert response.tenant_id == "tenant-x"


def test_capabilities_tenant_policy_override(monkeypatch):
    monkeypatch.setenv(
        "PAS_CAPABILITY_TENANT_OVERRIDES_JSON",
        (
            '{"tenant-a":{"policyVersion":"tenant-a-v7",'
            '"features":{"pas.ingestion.bulk_upload":false,"pas.support.lineage_api":false},'
            '"workflows":{"portfolio_bulk_onboarding":false},'
            '"supportedInputModes":{"PA":["pas_ref"],"default":["pas_ref"]}}}'
        ),
    )
    monkeypatch.setenv("PAS_CAP_UPLOAD_APIS_ENABLED", "true")

    service = CapabilitiesService()
    response = service.get_integration_capabilities(consumer_system="PA", tenant_id="tenant-a")
    feature_map = {feature.key: feature.enabled for feature in response.features}
    workflow_map = {workflow.workflow_key: workflow.enabled for workflow in response.workflows}

    assert response.policy_version == "tenant-a-v7"
    assert response.supported_input_modes == ["pas_ref"]
    assert feature_map["pas.ingestion.bulk_upload"] is False
    assert feature_map["pas.support.lineage_api"] is False
    assert workflow_map["portfolio_bulk_onboarding"] is False


def test_capabilities_ignores_invalid_tenant_policy_json(monkeypatch):
    monkeypatch.setenv("PAS_CAPABILITY_TENANT_OVERRIDES_JSON", "not-json")

    service = CapabilitiesService()
    response = service.get_integration_capabilities(consumer_system="BFF", tenant_id="tenant-a")

    assert response.policy_version == "tenant-default-v1"
    assert response.supported_input_modes == ["pas_ref"]
