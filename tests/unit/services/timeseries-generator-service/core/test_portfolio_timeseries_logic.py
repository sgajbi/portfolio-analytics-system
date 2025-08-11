# tests/unit/services/timeseries-generator-service/core/test_portfolio_timeseries_logic.py
import pytest
from unittest.mock import AsyncMock
from datetime import date
from decimal import Decimal

from portfolio_common.database_models import (
    Portfolio, PositionTimeseries, Cashflow, Instrument, FxRate, PortfolioTimeseries
)
from services.timeseries_generator_service.app.core.portfolio_timeseries_logic import PortfolioTimeseriesLogic, FxRateNotFoundError
from services.timeseries_generator_service.app.repositories.timeseries_repository import TimeseriesRepository

pytestmark = pytest.mark.asyncio
@pytest.fixture
def mock_repo() -> AsyncMock:
    """Provides a mock TimeseriesRepository."""
    # FIX: Explicitly make repository methods AsyncMocks to prevent warnings
    repo = AsyncMock(spec=TimeseriesRepository)
    repo.get_instruments_by_ids = AsyncMock()
    repo.get_fx_rate = AsyncMock()
    repo.get_last_portfolio_timeseries_before = AsyncMock()
    return repo

@pytest.fixture
def sample_portfolio() -> Portfolio:
    """A sample USD-based portfolio."""
    return Portfolio(portfolio_id="TS_PORT_01", base_currency="USD")

async def test_calculate_daily_record_multi_currency(mock_repo: AsyncMock, sample_portfolio: Portfolio):
    """
    Tests that the logic correctly aggregates position data from multiple currencies
    into the portfolio's base currency.
    """
    # ARRANGE
    test_date = date(2025, 8, 8)

    # 1. Mock the position-level time series data
    # - A USD position (no conversion needed)
    # - A EUR position (needs conversion)
    position_ts_list = [
        PositionTimeseries(
            security_id="SEC_USD", date=test_date, bod_market_value=Decimal("1000"),
            bod_cashflow=Decimal("0"), eod_cashflow=Decimal("50"), eod_market_value=Decimal("1100")
        ),
        PositionTimeseries(
            security_id="SEC_EUR", date=test_date, bod_market_value=Decimal("2000"),
            bod_cashflow=Decimal("-100"), eod_cashflow=Decimal("0"), eod_market_value=Decimal("2200")
        ),
    ]

    # 2. Mock portfolio-level cashflows (already in USD)
    portfolio_cashflows = [
        Cashflow(classification="EXPENSE", amount=Decimal("-25"), timing="EOD"),
        Cashflow(classification="CASHFLOW_IN", amount=Decimal("500"), timing="BOD"),
    ]
    
    # 3. Mock the necessary reference data for FX conversion
    mock_repo.get_instruments_by_ids.return_value = [
        Instrument(security_id="SEC_USD", currency="USD"),
        Instrument(security_id="SEC_EUR", currency="EUR"),
    ]
    mock_repo.get_fx_rate.return_value = FxRate(rate=Decimal("1.10")) # 1 EUR = 1.10 USD

    # 4. Mock the previous day's portfolio time series for BOD value
    mock_repo.get_last_portfolio_timeseries_before.return_value = PortfolioTimeseries(
        eod_market_value=Decimal("3000") # $1000 (USD pos) + €2000*0.9(hypothetical prev rate) = 2800. Let's use 3000 as a clean number.
    )

    # ACT
    result = await PortfolioTimeseriesLogic.calculate_daily_record(
        portfolio=sample_portfolio,
        a_date=test_date,
        position_timeseries_list=position_ts_list,
        portfolio_cashflows=portfolio_cashflows,
        repo=mock_repo
    )

    # ASSERT
    # BOD MV = From previous day's record
    assert result.bod_market_value == Decimal("3000")
    
    # BOD CF = $500 (portfolio) + (-€100 * 1.1) = 500 - 110 = $390
    assert result.bod_cashflow.quantize(Decimal("0.01")) == Decimal("390.00")

    # EOD CF = $50 (USD pos) + -$25 (portfolio fee) = $25
    assert result.eod_cashflow.quantize(Decimal("0.01")) == Decimal("25.00")

    # EOD MV = $1100 (USD pos) + (€2200 * 1.1) = 1100 + 2420 = $3520
    assert result.eod_market_value.quantize(Decimal("0.01")) == Decimal("3520.00")

    # Fees = abs(-25)
    assert result.fees == Decimal("25")
    
    # Verify FX rate was queried for the EUR position
    mock_repo.get_fx_rate.assert_called_once_with("EUR", "USD", test_date)

async def test_calculate_daily_record_raises_fx_error(mock_repo: AsyncMock, sample_portfolio: Portfolio):
    """
    Tests that a FxRateNotFoundError is raised if a required rate is missing.
    """
    # Arrange
    position_ts_list = [
        PositionTimeseries(security_id="SEC_EUR", date=date(2025, 8, 8))
    ]
    mock_repo.get_instruments_by_ids.return_value = [Instrument(security_id="SEC_EUR", currency="EUR")]
    mock_repo.get_fx_rate.return_value = None # Simulate missing rate

    # Act & Assert
    with pytest.raises(FxRateNotFoundError):
        await PortfolioTimeseriesLogic.calculate_daily_record(
            portfolio=sample_portfolio,
            a_date=date(2025, 8, 8),
            position_timeseries_list=position_ts_list,
            portfolio_cashflows=[],
            repo=mock_repo
        )