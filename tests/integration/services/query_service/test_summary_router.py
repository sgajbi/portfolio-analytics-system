# tests/integration/services/query_service/test_summary_router.py
import pytest
import pytest_asyncio
import httpx
from unittest.mock import AsyncMock
from datetime import date
from decimal import Decimal

from src.services.query_service.app.main import app
from src.services.query_service.app.services.summary_service import SummaryService
from src.services.query_service.app.dtos.summary_dto import (
    SummaryResponse, ResponseScope, WealthSummary, PnlSummary,
    IncomeSummary, ActivitySummary
)
from src.services.query_service.app.routers.summary import get_summary_service

pytestmark = pytest.mark.asyncio

@pytest_asyncio.fixture
async def async_test_client():
    """Provides an httpx.AsyncClient for the query service app with mocked dependencies."""
    mock_summary_service = AsyncMock(spec=SummaryService)
    
    mock_activity_summary = ActivitySummary(
        total_deposits=Decimal("10000"),
        total_withdrawals=Decimal("-2000"),
        total_transfers_in=Decimal("2000"),
        total_transfers_out=Decimal("-500"),
        total_fees=Decimal("-150")
    )
    
    mock_response = SummaryResponse(
        scope=ResponseScope(
            portfolio_id="P1",
            as_of_date=date(2025, 8, 29),
            period_start_date=date(2025, 1, 1),
            period_end_date=date(2025, 8, 29)
        ),
        wealth=WealthSummary(
            total_market_value=Decimal("125000"),
            total_cash=Decimal("25000")
        ),
        pnlSummary=PnlSummary(
            net_new_money=Decimal("10000"),
            realized_pnl=Decimal("1500"),
            unrealized_pnl_change=Decimal("5500"),
            total_pnl=Decimal("7000")
        ),
        incomeSummary=IncomeSummary(
            total_dividends=Decimal("300"),
            total_interest=Decimal("50")
        ),
        activitySummary=mock_activity_summary
    )
    mock_summary_service.get_portfolio_summary.return_value = mock_response

    # Override the dependency
    app.dependency_overrides[get_summary_service] = lambda: mock_summary_service
    
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, mock_summary_service
    
    # Clean up the override
    del app.dependency_overrides[get_summary_service]

async def test_get_portfolio_summary_success_all_sections(async_test_client):
    """
    GIVEN a valid request for all sections
    WHEN the /summary endpoint is called
    THEN it should return a 200 OK with the full data from the service.
    """
    client, mock_service = async_test_client
    portfolio_id = "P1"
    request_payload = {
        "as_of_date": "2025-08-29",
        "period": {"type": "YTD"},
        "sections": ["WEALTH", "PNL", "INCOME", "ACTIVITY"]
    }

    response = await client.post(f"/portfolios/{portfolio_id}/summary", json=request_payload)

    assert response.status_code == 200
    
    response_data = response.json()
    assert response_data["scope"]["portfolio_id"] == portfolio_id
    
    # --- FIX: Assert against floats instead of strings ---
    assert response_data["wealth"]["total_market_value"] == pytest.approx(125000.0)
    assert response_data["pnlSummary"]["total_pnl"] == pytest.approx(7000.0)
    assert response_data["incomeSummary"]["total_dividends"] == pytest.approx(300.0)
    assert response_data["activitySummary"]["total_fees"] == pytest.approx(-150.0)
    # --- END FIX ---

    mock_service.get_portfolio_summary.assert_awaited_once()

async def test_get_portfolio_summary_not_found(async_test_client):
    """
    GIVEN a request for a non-existent portfolio
    WHEN the service raises a ValueError
    THEN the endpoint should return a 404 Not Found.
    """
    client, mock_service = async_test_client
    portfolio_id = "P_NOT_FOUND"
    
    # Configure the mock to raise the expected exception
    mock_service.get_portfolio_summary.side_effect = ValueError(f"Portfolio {portfolio_id} not found")

    request_payload = {
        "as_of_date": "2025-08-29",
        "period": {"type": "YTD"},
        "sections": ["WEALTH"]
    }
    
    response = await client.post(f"/portfolios/{portfolio_id}/summary", json=request_payload)
    
    assert response.status_code == 404
    assert response.json()["detail"] == f"Portfolio {portfolio_id} not found"