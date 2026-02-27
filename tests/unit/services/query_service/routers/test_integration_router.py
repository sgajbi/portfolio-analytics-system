import pytest
from unittest.mock import MagicMock

from src.services.query_service.app.routers.integration import (
    get_effective_integration_policy,
    get_integration_service,
)
from src.services.query_service.app.services.integration_service import IntegrationService


@pytest.mark.asyncio
async def test_get_effective_integration_policy_router_function() -> None:
    mock_service = MagicMock(spec=IntegrationService)
    mock_service.get_effective_policy.return_value = {
        "contractVersion": "v1",
        "sourceService": "lotus-core",
        "consumerSystem": "lotus-manage",
        "tenantId": "tenant-a",
        "generatedAt": "2026-02-27T00:00:00Z",
        "policyProvenance": {
            "policyVersion": "tenant-default-v1",
            "policySource": "default",
            "matchedRuleId": "default",
            "strictMode": False,
        },
        "allowedSections": ["OVERVIEW"],
        "warnings": [],
    }

    response = await get_effective_integration_policy(
        consumer_system="lotus-manage",
        tenant_id="tenant-a",
        include_sections=["OVERVIEW"],
        integration_service=mock_service,
    )

    mock_service.get_effective_policy.assert_called_once_with(
        consumer_system="lotus-manage",
        tenant_id="tenant-a",
        include_sections=["OVERVIEW"],
    )
    assert response["consumerSystem"] == "lotus-manage"


def test_get_integration_service_factory_returns_service() -> None:
    service = get_integration_service(db=MagicMock())
    assert isinstance(service, IntegrationService)

