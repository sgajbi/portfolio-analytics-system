# tests/integration/services/query_service/test_review_router.py
import pytest
import pytest_asyncio
import httpx
from unittest.mock import AsyncMock, MagicMock
from datetime import date

from src.services.query_service.app.main import app
from src.services.query_service.app.services.review_service import ReviewService
from src.services.query_service.app.dtos.review_dto import PortfolioReviewResponse
from src.services.query_service.app.routers.review import get_review_service

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def async_test_client():
    """Provides an httpx.AsyncClient with the ReviewService dependency mocked."""
    # --- THIS IS THE FIX ---
    # The service class itself is not async, but its method is.
    # We use a synchronous MagicMock for the service instance and
    # an AsyncMock specifically for the async method.
    mock_review_service = MagicMock(spec=ReviewService)

    mock_response = PortfolioReviewResponse(portfolio_id="P1_MOCK", as_of_date=date(2025, 8, 30))
    # Configure the method as an async mock with a specific return value.
    mock_review_service.get_portfolio_review = AsyncMock(return_value=mock_response)
    # --- END FIX ---

    app.dependency_overrides[get_review_service] = lambda: mock_review_service

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, mock_review_service

    del app.dependency_overrides[get_review_service]


async def test_get_portfolio_review_success(async_test_client):
    """
    GIVEN a valid request
    WHEN the /review endpoint is called
    THEN it should return a 200 OK response from the mocked service.
    """
    client, mock_service = async_test_client
    portfolio_id = "P1_MOCK"
    request_payload = {"as_of_date": "2025-08-30", "sections": ["OVERVIEW"]}

    response = await client.post(f"/portfolios/{portfolio_id}/review", json=request_payload)

    assert response.status_code == 200
    response_data = response.json()
    assert response_data["portfolio_id"] == portfolio_id
    assert response_data["as_of_date"] == "2025-08-30"
    mock_service.get_portfolio_review.assert_awaited_once()


async def test_get_portfolio_review_not_found(async_test_client):
    """
    GIVEN a request for a non-existent portfolio
    WHEN the service raises a ValueError
    THEN the endpoint should return a 404 Not Found.
    """
    client, mock_service = async_test_client
    portfolio_id = "P_NOT_FOUND"

    # Configure the mock to raise the expected exception
    mock_service.get_portfolio_review.side_effect = ValueError(
        f"Portfolio {portfolio_id} not found"
    )

    request_payload = {"as_of_date": "2025-08-30", "sections": ["OVERVIEW"]}

    response = await client.post(f"/portfolios/{portfolio_id}/review", json=request_payload)

    assert response.status_code == 404
    assert response.json()["detail"] == f"Portfolio {portfolio_id} not found"


async def test_get_portfolio_review_unexpected_maps_to_500(async_test_client):
    client, mock_service = async_test_client
    portfolio_id = "P500"
    mock_service.get_portfolio_review.side_effect = RuntimeError("boom")

    request_payload = {"as_of_date": "2025-08-30", "sections": ["OVERVIEW"]}

    response = await client.post(f"/portfolios/{portfolio_id}/review", json=request_payload)

    assert response.status_code == 500
    assert "review generation" in response.json()["detail"].lower()
    assert "X-Correlation-ID" in response.headers
