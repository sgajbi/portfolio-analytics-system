# tests/unit/services/timeseries-generator-service/core/test_portfolio_timeseries_logic.py
import pytest
from unittest.mock import AsyncMock
from datetime import date
from decimal import Decimal

from portfolio_common.database_models import (
    Portfolio, PositionTimeseries, Instrument, FxRate, DailyPositionSnapshot
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
    repo.get_all_snapshots_for_date = AsyncMock()
    return repo

@pytest.fixture
def sample_portfolio() -> Portfolio:
    return Portfolio(portfolio_id="TS_PORT_01", base_currency="USD")

async def test_portfolio_logic_aggregates_correctly(mock_repo: AsyncMock, sample_portfolio: Portfolio):
    """
    Tests that the aggregation logic correctly sums portfolio cashflows and
    market values from the definitive snapshot source.
    """
    # ARRANGE
    test_date = date(2025, 8, 8)
    
    position_ts_list = [
        PositionTimeseries(
            security_id="CASH_USD", bod_cashflow_portfolio=Decimal(-25)
        ),
    ]
    
    snapshots_for_day = [
        DailyPositionSnapshot(security_id="SEC_AAPL", market_value=Decimal("10000")),
        DailyPositionSnapshot(security_id="CASH_USD", market_value=Decimal("50000")),
    ]

    mock_repo.get_instruments_by_ids.return_value = [Instrument(security_id="CASH_USD", currency="USD")]
    mock_repo.get_last_portfolio_timeseries_before.return_value = None
    mock_repo.get_all_snapshots_for_date.return_value = snapshots_for_day

    # ACT
    result = await PortfolioTimeseriesLogic.calculate_daily_record(
        portfolio=sample_portfolio,
        a_date=test_date,
        position_timeseries_list=position_ts_list,
        repo=mock_repo
    )

    # ASSERT
    mock_repo.get_all_snapshots_for_date.assert_awaited_once_with(sample_portfolio.portfolio_id, test_date)
    assert result.bod_cashflow == Decimal("-25")
    assert result.fees == Decimal("25")
    assert result.eod_market_value == Decimal("60000")