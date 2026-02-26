from datetime import UTC, date, datetime
from unittest.mock import MagicMock

import httpx
import pytest
import pytest_asyncio

from src.services.query_service.app.main import app
from src.services.query_service.app.routers.capabilities import (
    get_capabilities_service,
)
from src.services.query_service.app.services.capabilities_service import CapabilitiesService

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def async_test_client():
    mock_service = MagicMock()
    mock_service.get_integration_capabilities.return_value = {
        "contractVersion": "v1",
        "sourceService": "lotus-core",
        "consumerSystem": "lotus-manage",
        "tenantId": "tenant-1",
        "generatedAt": datetime(2026, 2, 23, tzinfo=UTC),
        "asOfDate": date(2026, 2, 23),
        "policyVersion": "tenant-1-v2",
        "supportedInputModes": ["pas_ref", "inline_bundle"],
        "features": [],
        "workflows": [],
    }
    app.dependency_overrides[get_capabilities_service] = lambda: mock_service
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, mock_service
    app.dependency_overrides.pop(get_capabilities_service, None)


async def test_capabilities_success(async_test_client):
    client, mock_service = async_test_client
    response = await client.get("/integration/capabilities?consumerSystem=lotus-manage&tenantId=tenant-1")
    assert response.status_code == 200
    body = response.json()
    assert body["consumerSystem"] == "lotus-manage"
    assert body["policyVersion"] == "tenant-1-v2"
    mock_service.get_integration_capabilities.assert_called_once_with(
        consumer_system="lotus-manage",
        tenant_id="tenant-1",
    )


def test_get_capabilities_service_returns_service_instance():
    service = get_capabilities_service()
    assert isinstance(service, CapabilitiesService)
