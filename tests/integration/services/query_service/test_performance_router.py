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


def performance_request_payload() -> dict:
    return {
        "scope": {"as_of_date": "2025-08-31", "net_or_gross": "NET"},
        "periods": [{"type": "YTD"}],
        "options": {
            "include_annualized": True,
            "include_cumulative": True,
            "include_attributes": False,
        },
    }


def mwr_request_payload() -> dict:
    return {
        "scope": {"as_of_date": "2025-08-31"},
        "periods": [{"type": "YTD"}],
        "options": {"annualize": True},
    }


async def test_performance_success(async_test_client):
    client = async_test_client

    response = await client.post(
        "/portfolios/P1/performance",
        json=performance_request_payload(),
        headers={"X-Correlation-ID": "corr-test-123"},
    )

    assert response.status_code == 410
    assert response.headers["X-Correlation-ID"] == "corr-test-123"
    detail = response.json()["detail"]
    assert detail["code"] == "PAS_LEGACY_ENDPOINT_REMOVED"
    assert detail["target_service"] == "lotus-performance"
    assert detail["target_endpoint"] == "/portfolios/{portfolio_id}/performance"


async def test_performance_not_found_maps_to_404(async_test_client):
    client = async_test_client

    response = await client.post("/portfolios/P404/performance", json=performance_request_payload())

    assert response.status_code == 410
    assert response.json()["detail"]["target_service"] == "lotus-performance"
    assert "X-Correlation-ID" in response.headers


async def test_performance_unexpected_maps_to_500(async_test_client):
    client = async_test_client

    response = await client.post("/portfolios/P500/performance", json=performance_request_payload())

    assert response.status_code == 410
    assert response.json()["detail"]["target_service"] == "lotus-performance"
    assert "X-Correlation-ID" in response.headers


async def test_mwr_success(async_test_client):
    client = async_test_client

    response = await client.post("/portfolios/P1/performance/mwr", json=mwr_request_payload())

    assert response.status_code == 410
    detail = response.json()["detail"]
    assert detail["target_service"] == "lotus-performance"
    assert detail["target_endpoint"] == "/portfolios/{portfolio_id}/performance/mwr"
    assert "X-Correlation-ID" in response.headers


async def test_mwr_not_found_maps_to_404(async_test_client):
    client = async_test_client

    response = await client.post("/portfolios/P404/performance/mwr", json=mwr_request_payload())

    assert response.status_code == 410
    assert response.json()["detail"]["target_service"] == "lotus-performance"
    assert "X-Correlation-ID" in response.headers


async def test_mwr_unexpected_maps_to_500(async_test_client):
    client = async_test_client

    response = await client.post("/portfolios/P500/performance/mwr", json=mwr_request_payload())

    assert response.status_code == 410
    assert response.json()["detail"]["target_service"] == "lotus-performance"
    assert "X-Correlation-ID" in response.headers
