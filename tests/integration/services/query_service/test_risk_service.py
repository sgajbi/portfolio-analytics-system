# tests/integration/services/query_service/test_risk_service.py
import pytest
import pytest_asyncio
import httpx
from datetime import date

from sqlalchemy.orm import Session
from src.services.query_service.app.main import app
from portfolio_common.database_models import Portfolio, PortfolioTimeseries, PositionState

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="function")
def setup_risk_integration_data(db_engine):
    """
    Seeds the database with a portfolio and a simple, deterministic
    time-series so we can easily verify the risk calculations.
    """
    portfolio_id = "RISK_INT_TEST_01"
    with Session(db_engine) as session:
        # Create prerequisite records
        session.add(
            Portfolio(
                portfolio_id=portfolio_id,
                base_currency="USD",
                open_date=date(2024, 1, 1),
                risk_exposure="a",
                investment_time_horizon="b",
                portfolio_type="c",
                booking_center="d",
                cif_id="e",
                status="f",
            )
        )
        # The query service depends on a PositionState record to find the current epoch
        session.add(
            PositionState(
                portfolio_id=portfolio_id,
                security_id="ANY_SEC",
                epoch=0,
                watermark_date=date(2024, 1, 1),
            )
        )

        # Create a simple, predictable time-series
        # Daily returns will be: +1%, +2%, -1%
        session.add_all(
            [
                PortfolioTimeseries(
                    portfolio_id=portfolio_id,
                    date=date(2025, 3, 3),
                    epoch=0,
                    bod_market_value=10000,
                    eod_market_value=10100,
                    bod_cashflow=0,
                    eod_cashflow=0,
                    fees=0,
                ),
                PortfolioTimeseries(
                    portfolio_id=portfolio_id,
                    date=date(2025, 3, 4),
                    epoch=0,
                    bod_market_value=10100,
                    eod_market_value=10302,
                    bod_cashflow=0,
                    eod_cashflow=0,
                    fees=0,
                ),
                PortfolioTimeseries(
                    portfolio_id=portfolio_id,
                    date=date(2025, 3, 5),
                    epoch=0,
                    bod_market_value=10302,
                    eod_market_value=10198.98,
                    bod_cashflow=0,
                    eod_cashflow=0,
                    fees=0,
                ),
            ]
        )
        session.commit()
    return {"portfolio_id": portfolio_id}


@pytest_asyncio.fixture
async def async_test_client():
    """Provides an httpx.AsyncClient for the query service app."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_risk_endpoint_happy_path(
    clean_db, setup_risk_integration_data, async_test_client: httpx.AsyncClient
):
    """
    GIVEN a portfolio with a known time-series
    WHEN the /risk endpoint is called
    THEN it should return a 410 Gone migration response.
    """
    # ARRANGE
    portfolio_id = setup_risk_integration_data["portfolio_id"]
    api_url = f"/portfolios/{portfolio_id}/risk"

    request_payload = {
        "scope": {"as_of_date": "2025-03-31"},
        "periods": [{"type": "YTD", "name": "TestPeriod"}],
        "metrics": ["VOLATILITY", "SHARPE"],
        "options": {"risk_free_mode": "ANNUAL_RATE", "risk_free_annual_rate": 0.01},
    }

    # ACT
    response = await async_test_client.post(api_url, json=request_payload)
    data = response.json()["detail"]

    # ASSERT
    assert response.status_code == 410
    assert data["code"] == "PAS_LEGACY_ENDPOINT_REMOVED"
    assert data["target_service"] == "PA"
    assert data["target_endpoint"] == "/portfolios/{portfolio_id}/risk"
