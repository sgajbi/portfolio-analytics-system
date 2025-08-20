# tests/unit/services/timeseries-generator-service/core/test_portfolio_timeseries_logic.py
import pytest
from unittest.mock import AsyncMock
from datetime import date
from decimal import Decimal

from portfolio_common.database_models import (
    Portfolio, PositionTimeseries, Instrument, FxRate
)
from services.timeseries_generator_service.app.core.portfolio_timeseries_logic import PortfolioTimeseriesLogic, FxRateNotFoundError
from src.services.timeseries_generator_service.app.repositories.timeseries_repository import TimeseriesRepository

pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_repo() -> AsyncMock:
    repo = AsyncMock(spec=TimeseriesRepository)
    repo.get_instruments_by_ids = AsyncMock()
    repo.get_fx_rate = AsyncMock()
    repo.get_last_portfolio_timeseries_before = AsyncMock()
    return repo

@pytest.fixture
def sample_portfolio() -> Portfolio:
    return Portfolio(portfolio_id="TS_PORT_01", base_currency="USD")

async def test_portfolio_logic_aggregates_only_portfolio_flows(mock_repo: AsyncMock, sample_portfolio: Portfolio):
    """
    Tests that the aggregation logic correctly sums ONLY the _portfolio columns,
    ignoring the _position columns for the final portfolio-level cashflow figures.
    """
    # ARRANGE
    test_date = date(2025, 8, 8)
    position_ts_list = [
        # Equity position with a position-only flow (e.g., a SELL)
        PositionTimeseries(
            security_id="SEC_AAPL", date=test_date, eod_market_value=Decimal("10000"),
            bod_cashflow_position=Decimal(0), eod_cashflow_position=Decimal(-5000),
            bod_cashflow_portfolio=Decimal(0), eod_cashflow_portfolio=Decimal(0)
        ),
        # Cash position with a portfolio flow (e.g., a FEE)
        PositionTimeseries(
            security_id="CASH_USD", date=test_date, eod_market_value=Decimal("50000"),
            bod_cashflow_position=Decimal(-25), eod_cashflow_position=Decimal(0),
            bod_cashflow_portfolio=Decimal(-25), eod_cashflow_portfolio=Decimal(0)
        ),
    ]
    mock_repo.get_instruments_by_ids.return_value = [
        Instrument(security_id="SEC_AAPL", currency="USD", product_type="Equity"),
        Instrument(security_id="CASH_USD", currency="USD", product_type="Cash"),
    ]
    mock_repo.get_last_portfolio_timeseries_before.return_value = None

    # ACT
    result = await PortfolioTimeseriesLogic.calculate_daily_record(
        portfolio=sample_portfolio,
        a_date=test_date,
        position_timeseries_list=position_ts_list,
        repo=mock_repo
    )

    # ASSERT
    # The portfolio cashflow should ONLY be the -25 from the cash position's portfolio column.
    # The -5000 from the equity's position column should be ignored for this calculation.
    assert result.bod_cashflow == Decimal("-25")
    assert result.eod_cashflow == Decimal("0")
    # Total EOD MV is the sum of all positions' EOD MVs
    assert result.eod_market_value == Decimal("60000")
    # Fees are derived from negative portfolio flows
    assert result.fees == Decimal("25")