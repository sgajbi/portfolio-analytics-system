import httpx
import pytest
import pytest_asyncio
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from portfolio_common.db import get_async_db_session
from src.services.query_service.app.dtos.mwr_dto import (
    MWRAttributes,
    MWRRequestScope,
    MWRResponse,
    MWRResult,
)
from src.services.query_service.app.dtos.performance_dto import (
    PerformanceRequestScope,
    PerformanceResponse,
    PerformanceResult,
)
from src.services.query_service.app.main import app

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def async_test_client():
    mock_perf_service = MagicMock()
    mock_perf_service.calculate_performance = AsyncMock()
    mock_mwr_service = MagicMock()
    mock_mwr_service.calculate_mwr = AsyncMock()

    app.dependency_overrides[get_async_db_session] = lambda: AsyncMock(spec=AsyncSession)

    with patch(
        "src.services.query_service.app.routers.performance.PerformanceService",
        return_value=mock_perf_service,
    ), patch(
        "src.services.query_service.app.routers.performance.MWRService",
        return_value=mock_mwr_service,
    ):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, mock_perf_service, mock_mwr_service

    app.dependency_overrides.pop(get_async_db_session, None)


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
    client, mock_perf_service, _ = async_test_client

    mock_perf_service.calculate_performance.return_value = PerformanceResponse(
        scope=PerformanceRequestScope(as_of_date=date(2025, 8, 31), net_or_gross="NET"),
        summary={
            "YTD": PerformanceResult(
                start_date=date(2025, 1, 1),
                end_date=date(2025, 8, 31),
                cumulative_return=5.1,
            )
        },
    )

    response = await client.post(
        "/portfolios/P1/performance",
        json=performance_request_payload(),
        headers={"X-Correlation-ID": "corr-test-123"},
    )

    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == "corr-test-123"
    assert response.json()["summary"]["YTD"]["cumulative_return"] == 5.1


async def test_performance_not_found_maps_to_404(async_test_client):
    client, mock_perf_service, _ = async_test_client
    mock_perf_service.calculate_performance.side_effect = ValueError("Portfolio P404 not found")

    response = await client.post("/portfolios/P404/performance", json=performance_request_payload())

    assert response.status_code == 404
    assert response.json()["detail"] == "Portfolio P404 not found"
    assert "X-Correlation-ID" in response.headers


async def test_performance_unexpected_maps_to_500(async_test_client):
    client, mock_perf_service, _ = async_test_client
    mock_perf_service.calculate_performance.side_effect = RuntimeError("unexpected")

    response = await client.post("/portfolios/P500/performance", json=performance_request_payload())

    assert response.status_code == 500
    assert "unexpected server error occurred" in response.json()["detail"].lower()
    assert "X-Correlation-ID" in response.headers


async def test_mwr_success(async_test_client):
    client, _, mock_mwr_service = async_test_client
    mock_mwr_service.calculate_mwr.return_value = MWRResponse(
        scope=MWRRequestScope(as_of_date=date(2025, 8, 31)),
        summary={
            "YTD": MWRResult(
                start_date=date(2025, 1, 1),
                end_date=date(2025, 8, 31),
                mwr=4.2,
                mwr_annualized=4.2,
                attributes=MWRAttributes(
                    begin_market_value=1000,
                    end_market_value=1042,
                    external_contributions=0,
                    external_withdrawals=0,
                    cashflow_count=0,
                ),
            )
        },
    )

    response = await client.post("/portfolios/P1/performance/mwr", json=mwr_request_payload())

    assert response.status_code == 200
    assert response.json()["summary"]["YTD"]["mwr"] == 4.2
    assert "X-Correlation-ID" in response.headers


async def test_mwr_not_found_maps_to_404(async_test_client):
    client, _, mock_mwr_service = async_test_client
    mock_mwr_service.calculate_mwr.side_effect = ValueError("Portfolio P404 not found")

    response = await client.post("/portfolios/P404/performance/mwr", json=mwr_request_payload())

    assert response.status_code == 404
    assert response.json()["detail"] == "Portfolio P404 not found"
    assert "X-Correlation-ID" in response.headers


async def test_mwr_unexpected_maps_to_500(async_test_client):
    client, _, mock_mwr_service = async_test_client
    mock_mwr_service.calculate_mwr.side_effect = RuntimeError("unexpected")

    response = await client.post("/portfolios/P500/performance/mwr", json=mwr_request_payload())

    assert response.status_code == 500
    assert "unexpected server error occurred" in response.json()["detail"].lower()
    assert "X-Correlation-ID" in response.headers
