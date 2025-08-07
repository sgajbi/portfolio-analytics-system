import pytest
from decimal import Decimal
from datetime import date

from core.position_timeseries_logic import PositionTimeseriesLogic
from portfolio_common.database_models import DailyPositionSnapshot, PositionTimeseries

@pytest.fixture
def current_snapshot() -> DailyPositionSnapshot:
    """A fixture for the current day's position snapshot."""
    return DailyPositionSnapshot(
        portfolio_id="P1",
        security_id="S1",
        date=date(2025, 7, 29),
        quantity=Decimal("100"),
        cost_basis=Decimal("10000"),
        market_value=Decimal("12000")
    )

@pytest.fixture
def previous_day_timeseries() -> PositionTimeseries:
    """A fixture for the previous day's time series record."""
    return PositionTimeseries(
        portfolio_id="P1",
        security_id="S1",
        date=date(2025, 7, 28),
        eod_market_value=Decimal("11500")
    )

def test_calculate_daily_record_first_day(current_snapshot):
    """
    Tests calculating a time series record when there is no previous day's record.
    BOD market value should be zero.
    """
    new_record = PositionTimeseriesLogic.calculate_daily_record(
        current_snapshot=current_snapshot,
        previous_timeseries=None,
        bod_cashflow=Decimal("-10000"), # e.g., initial purchase
        eod_cashflow=Decimal("0")
    )

    assert new_record.portfolio_id == "P1"
    assert new_record.security_id == "S1"
    assert new_record.date == date(2025, 7, 29)
    assert new_record.bod_market_value == Decimal("0") # First day
    assert new_record.bod_cashflow == Decimal("-10000")
    assert new_record.eod_cashflow == Decimal("0")
    assert new_record.eod_market_value == Decimal("12000") # From snapshot
    assert new_record.quantity == Decimal("100") # From snapshot
    assert new_record.cost == Decimal("100") # 10000 cost_basis / 100 quantity

def test_calculate_daily_record_subsequent_day(current_snapshot, previous_day_timeseries):
    """
    Tests that a subsequent day's BOD market value equals the previous day's EOD market value.
    """
    new_record = PositionTimeseriesLogic.calculate_daily_record(
        current_snapshot=current_snapshot,
        previous_timeseries=previous_day_timeseries,
        bod_cashflow=Decimal("0"),
        eod_cashflow=Decimal("50") # e.g., dividend
    )

    # Key assertion: BOD value carries over from previous EOD
    assert new_record.bod_market_value == previous_day_timeseries.eod_market_value
    assert new_record.bod_market_value == Decimal("11500")

    assert new_record.eod_market_value == Decimal("12000")
    assert new_record.eod_cashflow == Decimal("50")