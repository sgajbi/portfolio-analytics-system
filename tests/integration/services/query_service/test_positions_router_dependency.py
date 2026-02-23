from datetime import date
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio

from src.services.query_service.app.main import app
from src.services.query_service.app.routers.positions import get_position_service

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def async_test_client():
    mock_service = AsyncMock()
    app.dependency_overrides[get_position_service] = lambda: mock_service
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, mock_service
    app.dependency_overrides.pop(get_position_service, None)


async def test_get_position_history_success(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_position_history.return_value = {
        "portfolio_id": "P1",
        "security_id": "S1",
        "positions": [
            {
                "position_date": date(2025, 1, 1),
                "transaction_id": "T1",
                "quantity": 10.0,
                "cost_basis": 1000.0,
                "cost_basis_local": 1000.0,
                "valuation": None,
                "reprocessing_status": "CURRENT",
            }
        ],
    }

    response = await client.get("/portfolios/P1/position-history?security_id=S1")

    assert response.status_code == 200
    assert response.json()["security_id"] == "S1"
    assert "X-Correlation-ID" in response.headers


async def test_get_position_history_unexpected_maps_to_500(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_position_history.side_effect = RuntimeError("boom")

    response = await client.get("/portfolios/P1/position-history?security_id=S1")

    assert response.status_code == 500
    assert "unexpected error" in response.json()["detail"].lower()


async def test_get_latest_positions_success(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_portfolio_positions.return_value = {
        "portfolio_id": "P1",
        "positions": [
            {
                "security_id": "S1",
                "quantity": 15.0,
                "instrument_name": "A",
                "position_date": date(2025, 1, 1),
                "asset_class": "Equity",
                "cost_basis": 1300.0,
                "cost_basis_local": 1300.0,
                "valuation": None,
                "reprocessing_status": "CURRENT",
            }
        ],
    }

    response = await client.get("/portfolios/P1/positions")

    assert response.status_code == 200
    assert response.json()["portfolio_id"] == "P1"


async def test_get_latest_positions_unexpected_maps_to_500(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_portfolio_positions.side_effect = RuntimeError("boom")

    response = await client.get("/portfolios/P1/positions")

    assert response.status_code == 500
    assert "unexpected error" in response.json()["detail"].lower()
