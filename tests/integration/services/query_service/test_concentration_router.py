# tests/integration/services/query_service/test_concentration_router.py
import pytest
import pytest_asyncio
import httpx
from unittest.mock import AsyncMock
from datetime import date

from src.services.query_service.app.main import app
from src.services.query_service.app.services.concentration_service import get_concentration_service, ConcentrationService
from src.services.query_service.app.dtos.concentration_dto import ConcentrationResponse, ConcentrationRequestScope, ResponseSummary

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def async_test_client():
    """Provides an httpx.AsyncClient with the ConcentrationService dependency mocked."""
    
    mock_service = AsyncMock(spec=ConcentrationService)
    mock_response = ConcentrationResponse(
        scope=ConcentrationRequestScope(
            as_of_date=date(2025, 8, 31),
            reporting_currency="USD"
        ),
        summary=ResponseSummary(portfolio_market_value=100000.0, findings=[])
    )
    mock_service.calculate_concentration.return_value = mock_response

    app.dependency_overrides[get_concentration_service] = lambda: mock_service
    
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, mock_service
    
    del app.dependency_overrides[get_concentration_service]


async def test_calculate_concentration_success(async_test_client):
    """
    GIVEN a valid request to the /concentration endpoint
    WHEN the service layer returns a valid response
    THEN the router should return a 200 OK with the correct data.
    """
    client, mock_service = async_test_client
    portfolio_id = "P1_MOCK"
    request_payload = {
        "scope": {"as_of_date": "2025-08-31"},
        "metrics": ["BULK"]
    }

    response = await client.post(f"/portfolios/{portfolio_id}/concentration", json=request_payload)

    assert response.status_code == 200
    response_data = response.json()
    assert response_data["scope"]["as_of_date"] == "2025-08-31"
    assert response_data["summary"]["portfolio_market_value"] == 100000.0
    
    mock_service.calculate_concentration.assert_awaited_once()


async def test_calculate_concentration_portfolio_not_found(async_test_client):
    """
    GIVEN a request for a portfolio that does not exist
    WHEN the service layer raises a ValueError
    THEN the router should return a 404 Not Found response.
    """
    client, mock_service = async_test_client
    portfolio_id = "P_NOT_FOUND"
    
    mock_service.calculate_concentration.side_effect = ValueError(f"Portfolio {portfolio_id} not found")

    request_payload = {
        "scope": {"as_of_date": "2025-08-31"},
        "metrics": ["BULK"]
    }
    
    response = await client.post(f"/portfolios/{portfolio_id}/concentration", json=request_payload)
    
    assert response.status_code == 404
    assert response.json()["detail"] == f"Portfolio {portfolio_id} not found"


async def test_calculate_concentration_unexpected_error(async_test_client):
    client, mock_service = async_test_client
    mock_service.calculate_concentration.side_effect = RuntimeError("boom")

    request_payload = {"scope": {"as_of_date": "2025-08-31"}, "metrics": ["BULK"]}
    response = await client.post("/portfolios/P1/concentration", json=request_payload)

    assert response.status_code == 500
    assert "concentration calculation" in response.json()["detail"].lower()
