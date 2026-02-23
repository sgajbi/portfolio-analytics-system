import httpx
import pytest
import pytest_asyncio
from datetime import date
from unittest.mock import AsyncMock

from src.services.query_service.app.dtos.risk_dto import (
    RiskPeriodResult,
    RiskRequestScope,
    RiskResponse,
    RiskValue,
)
from src.services.query_service.app.main import app
from src.services.query_service.app.routers.risk import get_risk_service

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def async_test_client():
    mock_risk_service = AsyncMock()
    app.dependency_overrides[get_risk_service] = lambda: mock_risk_service
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, mock_risk_service
    app.dependency_overrides.pop(get_risk_service, None)


def risk_request_payload() -> dict:
    return {
        "scope": {"as_of_date": "2025-08-31", "net_or_gross": "NET"},
        "periods": [{"type": "YTD"}],
        "metrics": ["VOLATILITY"],
        "options": {"frequency": "DAILY"},
    }


async def test_risk_success(async_test_client):
    client, mock_risk_service = async_test_client
    mock_risk_service.calculate_risk.return_value = RiskResponse(
        scope=RiskRequestScope(as_of_date=date(2025, 8, 31), net_or_gross="NET"),
        results={
            "YTD": RiskPeriodResult(
                start_date=date(2025, 1, 1),
                end_date=date(2025, 8, 31),
                metrics={"VOLATILITY": RiskValue(value=0.12)},
            )
        },
    )

    response = await client.post("/portfolios/P1/risk", json=risk_request_payload())

    assert response.status_code == 200
    assert response.json()["results"]["YTD"]["metrics"]["VOLATILITY"]["value"] == 0.12
    assert "X-Correlation-ID" in response.headers


async def test_risk_not_found_maps_to_404(async_test_client):
    client, mock_risk_service = async_test_client
    mock_risk_service.calculate_risk.side_effect = ValueError("Portfolio missing")

    response = await client.post("/portfolios/P404/risk", json=risk_request_payload())

    assert response.status_code == 404
    assert response.json()["detail"] == "Portfolio missing"


async def test_risk_unexpected_maps_to_500(async_test_client):
    client, mock_risk_service = async_test_client
    mock_risk_service.calculate_risk.side_effect = RuntimeError("boom")

    response = await client.post("/portfolios/P500/risk", json=risk_request_payload())

    assert response.status_code == 500
    assert "risk calculation" in response.json()["detail"].lower()
