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

async def test_portfolio_logic_aggregates_correctly_with_epoch(mock_repo: AsyncMock, sample_portfolio: Portfolio):
    """
    Tests that aggregation logic correctly sums market values from snapshots
    of the correct epoch and tags the result with that epoch.
    """
    # ARRANGE
    test_date = date(2025, 8, 8)
    target_epoch = 2
    
    position_ts_list = [
        PositionTimeseries(security_id="CASH_USD", bod_cashflow_portfolio=Decimal(-25))
    ]
    
    # Simulate snapshots from different epochs; only epoch 2 should be included
    snapshots_for_day = [
        DailyPositionSnapshot(security_id="SEC_AAPL", market_value=Decimal("10000"), epoch=2),
        DailyPositionSnapshot(security_id="CASH_USD", market_value=Decimal("50000"), epoch=2),
        DailyPositionSnapshot(security_id="SEC_OLD", market_value=Decimal("99999"), epoch=1), # Should be ignored
    ]

    mock_repo.get_instruments_by_ids.return_value = [Instrument(security_id="CASH_USD", currency="USD")]
    mock_repo.get_last_portfolio_timeseries_before.return_value = None
    mock_repo.get_all_snapshots_for_date.return_value = snapshots_for_day

    # ACT
    result = await PortfolioTimeseriesLogic.calculate_daily_record(
        portfolio=sample_portfolio,
        a_date=test_date,
        epoch=target_epoch,
        position_timeseries_list=position_ts_list,
        repo=mock_repo
    )

    # ASSERT
    assert result.epoch == target_epoch
    assert result.eod_market_value == Decimal("60000") # 10000 + 50000