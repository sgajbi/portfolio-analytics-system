from datetime import date
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio

from src.services.query_service.app.main import app
from src.services.query_service.app.routers.integration import get_integration_service

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def async_test_client():
    mock_service = AsyncMock()
    app.dependency_overrides[get_integration_service] = lambda: mock_service
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, mock_service
    app.dependency_overrides.pop(get_integration_service, None)


def snapshot_request_payload() -> dict:
    return {
        "asOfDate": "2026-02-23",
        "includeSections": ["OVERVIEW", "HOLDINGS"],
        "consumerSystem": "PA",
    }


async def test_integration_snapshot_success(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_portfolio_core_snapshot.return_value = {
        "contractVersion": "v1",
        "consumerSystem": "PA",
        "portfolio": {
            "portfolio_id": "P1",
            "base_currency": "USD",
            "open_date": date(2025, 1, 1),
            "close_date": None,
            "risk_exposure": "MODERATE",
            "investment_time_horizon": "LONG_TERM",
            "portfolio_type": "DISCRETIONARY",
            "objective": "GROWTH",
            "booking_center": "LON-01",
            "cif_id": "CIF-1",
            "is_leverage_allowed": False,
            "advisor_id": "ADV-1",
            "status": "ACTIVE",
        },
        "snapshot": {
            "portfolio_id": "P1",
            "as_of_date": date(2026, 2, 23),
            "overview": None,
            "allocation": None,
            "performance": None,
            "riskAnalytics": None,
            "incomeAndActivity": None,
            "holdings": None,
            "transactions": None,
        },
    }

    response = await client.post(
        "/integration/portfolios/P1/core-snapshot", json=snapshot_request_payload()
    )

    assert response.status_code == 200
    assert response.json()["contractVersion"] == "v1"
    assert "X-Correlation-ID" in response.headers


async def test_integration_snapshot_not_found_maps_to_404(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_portfolio_core_snapshot.side_effect = ValueError("Portfolio not found")

    response = await client.post(
        "/integration/portfolios/P404/core-snapshot", json=snapshot_request_payload()
    )

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


async def test_integration_snapshot_unexpected_maps_to_500(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_portfolio_core_snapshot.side_effect = RuntimeError("boom")

    response = await client.post(
        "/integration/portfolios/P500/core-snapshot", json=snapshot_request_payload()
    )

    assert response.status_code == 500
    assert "integration snapshot" in response.json()["detail"].lower()
