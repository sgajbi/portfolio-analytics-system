from src.services.query_service.app.services.capabilities_service import CapabilitiesService


def test_capabilities_default_flags(monkeypatch):
    monkeypatch.delenv("PAS_CAP_CORE_SNAPSHOT_ENABLED", raising=False)
    monkeypatch.delenv("PAS_CAP_UPLOAD_APIS_ENABLED", raising=False)
    monkeypatch.delenv("PAS_POLICY_VERSION", raising=False)

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

    service = CapabilitiesService()
    response = service.get_integration_capabilities(consumer_system="PA", tenant_id="tenant-x")

    feature_map = {feature.key: feature.enabled for feature in response.features}
    assert feature_map["pas.ingestion.bulk_upload"] is False
    assert response.policy_version == "tenant-x-v3"
    assert set(response.supported_input_modes) == {"pas_ref", "inline_bundle"}
    assert response.tenant_id == "tenant-x"
