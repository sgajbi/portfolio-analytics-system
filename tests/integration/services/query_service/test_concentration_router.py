# tests/integration/services/query_service/test_concentration_router.py
import pytest
import pytest_asyncio
import httpx
from unittest.mock import AsyncMock

from src.services.query_service.app.main import app
from src.services.query_service.app.services.concentration_service import get_concentration_service, ConcentrationService

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def async_test_client():
    """Provides an httpx.AsyncClient with the ConcentrationService dependency mocked."""
    
    mock_service = AsyncMock(spec=ConcentrationService)

    app.dependency_overrides[get_concentration_service] = lambda: mock_service
    
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, mock_service
    
    del app.dependency_overrides[get_concentration_service]


async def test_calculate_concentration_success(async_test_client):
    """
    GIVEN a valid request to the /concentration endpoint
    WHEN the service layer returns a valid response
    THEN the router should return a 410 Gone with migration metadata.
    """
    client, mock_service = async_test_client
    portfolio_id = "P1_MOCK"
    request_payload = {
        "scope": {"as_of_date": "2025-08-31"},
        "metrics": ["BULK"]
    }

    response = await client.post(f"/portfolios/{portfolio_id}/concentration", json=request_payload)

    assert response.status_code == 410
    detail = response.json()["detail"]
    assert detail["code"] == "PAS_LEGACY_ENDPOINT_REMOVED"
    assert detail["target_service"] == "PA"
    assert detail["target_endpoint"] == "/portfolios/{portfolio_id}/concentration"
    
    mock_service.calculate_concentration.assert_not_awaited()


async def test_calculate_concentration_portfolio_not_found(async_test_client):
    """
    GIVEN a request for a portfolio that does not exist
    THEN the router should still return a 410 Gone response.
    """
    client, mock_service = async_test_client
    portfolio_id = "P_NOT_FOUND"
    
    request_payload = {
        "scope": {"as_of_date": "2025-08-31"},
        "metrics": ["BULK"]
    }
    
    response = await client.post(f"/portfolios/{portfolio_id}/concentration", json=request_payload)
    
    assert response.status_code == 410
    assert response.json()["detail"]["target_service"] == "PA"
    mock_service.calculate_concentration.assert_not_awaited()


async def test_calculate_concentration_unexpected_error(async_test_client):
    client, mock_service = async_test_client

    request_payload = {"scope": {"as_of_date": "2025-08-31"}, "metrics": ["BULK"]}
    response = await client.post("/portfolios/P1/concentration", json=request_payload)

    assert response.status_code == 410
    assert response.json()["detail"]["target_service"] == "PA"
    mock_service.calculate_concentration.assert_not_awaited()
