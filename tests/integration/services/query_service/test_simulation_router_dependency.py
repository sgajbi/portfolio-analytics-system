from datetime import datetime, timezone
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio

from src.services.query_service.app.main import app
from src.services.query_service.app.routers.simulation import get_simulation_service

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def async_test_client():
    mock_service = AsyncMock()
    app.dependency_overrides[get_simulation_service] = lambda: mock_service
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, mock_service
    app.dependency_overrides.pop(get_simulation_service, None)


async def test_create_simulation_session_success(async_test_client):
    client, mock_service = async_test_client
    now = datetime.now(timezone.utc)
    mock_service.create_session.return_value = {
        "session": {
            "session_id": "S1",
            "portfolio_id": "P1",
            "status": "ACTIVE",
            "version": 1,
            "created_by": "tester",
            "created_at": now,
            "expires_at": now,
        }
    }

    response = await client.post(
        "/simulation-sessions", json={"portfolio_id": "P1", "created_by": "tester"}
    )

    assert response.status_code == 201
    assert response.json()["session"]["session_id"] == "S1"


async def test_get_simulation_session_not_found_maps_to_404(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_session.side_effect = ValueError("not found")

    response = await client.get("/simulation-sessions/S404")

    assert response.status_code == 404


async def test_add_simulation_changes_validation_maps_to_400(async_test_client):
    client, mock_service = async_test_client
    mock_service.add_changes.side_effect = ValueError("session expired")

    response = await client.post(
        "/simulation-sessions/S1/changes",
        json={"changes": [{"security_id": "SEC_AAPL_US", "transaction_type": "BUY", "quantity": 10}]},
    )

    assert response.status_code == 400


async def test_get_projected_positions_success(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_projected_positions.return_value = {
        "session_id": "S1",
        "portfolio_id": "P1",
        "baseline_as_of": None,
        "positions": [
            {
                "security_id": "SEC_AAPL_US",
                "instrument_name": "Apple Inc.",
                "asset_class": "Equity",
                "baseline_quantity": 100.0,
                "proposed_quantity": 120.0,
                "delta_quantity": 20.0,
                "cost_basis": 1000.0,
                "cost_basis_local": 1000.0,
            }
        ],
    }

    response = await client.get("/simulation-sessions/S1/projected-positions")

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == "S1"
    assert body["positions"][0]["delta_quantity"] == 20.0
