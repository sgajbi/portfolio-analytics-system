# tests/integration/services/query_service/test_summary_router.py
import pytest
import pytest_asyncio
import httpx

from src.services.query_service.app.main import app

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def async_test_client():
    """Provides an httpx.AsyncClient for the query service app with mocked dependencies."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_get_portfolio_summary_success_all_sections(async_test_client):
    """
    GIVEN a valid request for all sections
    WHEN the /summary endpoint is called
    THEN it should return a 410 Gone with migration metadata.
    """
    client = async_test_client
    portfolio_id = "P1"
    request_payload = {
        "as_of_date": "2025-08-29",
        "period": {"type": "YTD"},
        "sections": ["WEALTH", "PNL", "INCOME", "ACTIVITY"],
    }

    response = await client.post(f"/portfolios/{portfolio_id}/summary", json=request_payload)

    assert response.status_code == 410
    detail = response.json()["detail"]
    assert detail["code"] == "PAS_LEGACY_ENDPOINT_REMOVED"
    assert detail["target_service"] == "lotus-report"
    assert detail["target_endpoint"] == "/reports/portfolios/{portfolio_id}/summary"


async def test_get_portfolio_summary_not_found(async_test_client):
    """
    GIVEN a request for a non-existent portfolio
    THEN the endpoint should return a 410 Gone.
    """
    client = async_test_client
    portfolio_id = "P_NOT_FOUND"

    request_payload = {
        "as_of_date": "2025-08-29",
        "period": {"type": "YTD"},
        "sections": ["WEALTH"],
    }

    response = await client.post(f"/portfolios/{portfolio_id}/summary", json=request_payload)

    assert response.status_code == 410
    assert response.json()["detail"]["target_service"] == "lotus-report"


async def test_get_portfolio_summary_unexpected_error_maps_to_500(async_test_client):
    client = async_test_client

    request_payload = {
        "as_of_date": "2025-08-29",
        "period": {"type": "YTD"},
        "sections": ["WEALTH"],
    }

    response = await client.post("/portfolios/P1/summary", json=request_payload)

    assert response.status_code == 410
    assert response.json()["detail"]["target_service"] == "lotus-report"
