import httpx
import pytest
import pytest_asyncio

from src.services.query_service.app.main import app

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def async_test_client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def risk_request_payload() -> dict:
    return {
        "scope": {"as_of_date": "2025-08-31", "net_or_gross": "NET"},
        "periods": [{"type": "YTD"}],
        "metrics": ["VOLATILITY"],
        "options": {"frequency": "DAILY"},
    }


async def test_risk_success(async_test_client):
    client = async_test_client

    response = await client.post("/portfolios/P1/risk", json=risk_request_payload())

    assert response.status_code == 410
    detail = response.json()["detail"]
    assert detail["code"] == "PAS_LEGACY_ENDPOINT_REMOVED"
    assert detail["target_service"] == "PA"
    assert detail["target_endpoint"] == "/portfolios/{portfolio_id}/risk"
    assert "X-Correlation-ID" in response.headers


async def test_risk_not_found_maps_to_404(async_test_client):
    client = async_test_client

    response = await client.post("/portfolios/P404/risk", json=risk_request_payload())

    assert response.status_code == 410
    assert response.json()["detail"]["target_service"] == "PA"


async def test_risk_unexpected_maps_to_500(async_test_client):
    client = async_test_client

    response = await client.post("/portfolios/P500/risk", json=risk_request_payload())

    assert response.status_code == 410
    assert response.json()["detail"]["target_service"] == "PA"
