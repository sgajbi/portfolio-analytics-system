# tests/integration/services/query_service/test_review_router.py
import pytest
import pytest_asyncio
import httpx
from src.services.query_service.app.main import app

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def async_test_client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_get_portfolio_review_success(async_test_client):
    """
    GIVEN a valid request
    WHEN the /review endpoint is called
    THEN it should return a 410 Gone response.
    """
    client = async_test_client
    portfolio_id = "P1_MOCK"
    request_payload = {"as_of_date": "2025-08-30", "sections": ["OVERVIEW"]}

    response = await client.post(f"/portfolios/{portfolio_id}/review", json=request_payload)

    assert response.status_code == 410
    detail = response.json()["detail"]
    assert detail["code"] == "PAS_LEGACY_ENDPOINT_REMOVED"
    assert detail["target_service"] == "RAS"
    assert detail["target_endpoint"] == "/reports/portfolios/{portfolio_id}/review"


async def test_get_portfolio_review_not_found(async_test_client):
    """
    GIVEN a request for a non-existent portfolio
    THEN the endpoint should return a 410 Gone.
    """
    client = async_test_client
    portfolio_id = "P_NOT_FOUND"

    request_payload = {"as_of_date": "2025-08-30", "sections": ["OVERVIEW"]}

    response = await client.post(f"/portfolios/{portfolio_id}/review", json=request_payload)

    assert response.status_code == 410
    assert response.json()["detail"]["target_service"] == "RAS"


async def test_get_portfolio_review_unexpected_maps_to_500(async_test_client):
    client = async_test_client
    portfolio_id = "P500"

    request_payload = {"as_of_date": "2025-08-30", "sections": ["OVERVIEW"]}

    response = await client.post(f"/portfolios/{portfolio_id}/review", json=request_payload)

    assert response.status_code == 410
    assert response.json()["detail"]["target_service"] == "RAS"
    assert "X-Correlation-ID" in response.headers
