# tests/integration/services/query_service/test_position_analytics_router.py
import pytest
import pytest_asyncio
import httpx
from unittest.mock import AsyncMock, MagicMock
from datetime import date

from src.services.query_service.app.main import app
from src.services.query_service.app.services.position_analytics_service import (
    PositionAnalyticsService, get_position_analytics_service
)
from src.services.query_service.app.dtos.position_analytics_dto import PositionAnalyticsResponse

pytestmark = pytest.mark.asyncio

@pytest_asyncio.fixture
async def async_test_client():
    """Provides an httpx.AsyncClient with the PositionAnalyticsService dependency mocked."""
    mock_service = MagicMock(spec=PositionAnalyticsService)
    
    mock_response = PositionAnalyticsResponse(
        portfolioId="P1_MOCK",
        asOfDate=date(2025, 8, 31),
        totalMarketValue=12345.67,
        positions=[]
    )
    mock_service.get_position_analytics = AsyncMock(return_value=mock_response)

    app.dependency_overrides[get_position_analytics_service] = lambda: mock_service
    
    transport = httpx.ASGITransport(app=app)
    async with httpx.ASGITransport(app=app) as transport:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, mock_service
    
    del app.dependency_overrides[get_position_analytics_service]


async def test_get_position_analytics_success(async_test_client):
    """
    GIVEN a valid request to the /positions-analytics endpoint
    WHEN the service layer returns a valid response
    THEN the router should return a 200 OK with the correct data.
    """
    client, mock_service = async_test_client
    portfolio_id = "P1_MOCK"
    request_payload = {
        "asOfDate": "2025-08-31",
        "sections": ["BASE", "VALUATION"]
    }

    response = await client.post(f"/portfolios/{portfolio_id}/positions-analytics", json=request_payload)

    assert response.status_code == 200
    response_data = response.json()
    assert response_data["portfolioId"] == portfolio_id
    assert response_data["asOfDate"] == "2025-08-31"
    assert response_data["totalMarketValue"] == 12345.67
    
    mock_service.get_position_analytics.assert_awaited_once()

async def test_get_position_analytics_portfolio_not_found(async_test_client):
    """
    GIVEN a request for a portfolio that does not exist
    WHEN the service layer raises a ValueError
    THEN the router should return a 404 Not Found response.
    """
    client, mock_service = async_test_client
    portfolio_id = "P_NOT_FOUND"
    
    mock_service.get_position_analytics.side_effect = ValueError(f"Portfolio {portfolio_id} not found")

    request_payload = {
        "asOfDate": "2025-08-31",
        "sections": ["BASE"]
    }
    
    response = await client.post(f"/portfolios/{portfolio_id}/positions-analytics", json=request_payload)
    
    assert response.status_code == 404
    assert response.json()["detail"] == f"Portfolio {portfolio_id} not found"