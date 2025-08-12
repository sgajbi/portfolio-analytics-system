# tests/unit/services/timeseries-generator-service/core/test_position_timeseries_logic.py
import pytest
from decimal import Decimal
from datetime import date

# Corrected absolute import
from src.services.timeseries_generator_service.app.core.position_timeseries_logic import PositionTimeseriesLogic
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
        market_value=Decimal("12500"), # Base currency value
        market_value_local=Decimal("12000") # Local currency value
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
    assert new_record.eod_market_value == Decimal("12000") # From snapshot's market_value_local
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
        eod_cashflow=Decimal("0")
    )

    # Key assertion: BOD value carries over from previous EOD
    assert new_record.bod_market_value == previous_day_timeseries.eod_market_value
    assert new_record.bod_market_value == Decimal("11500")
    assert new_record.eod_market_value == Decimal("12000")

def test_calculate_daily_record_with_bod_and_eod_cashflows(current_snapshot, previous_day_timeseries):
    """
    Tests that BOD (e.g., dividend) and EOD (e.g., partial sell) cashflows
    are correctly assigned in the final time series record.
    """
    # ARRANGE: Simulate a $50 dividend (BOD inflow) and a $1200 partial sell (EOD inflow)
    bod_inflow = Decimal("50")
    eod_inflow = Decimal("1200")

    # The snapshot reflects the EOD state *after* the partial sell.
    current_snapshot.quantity = Decimal("90") # 10 shares were sold
    current_snapshot.market_value_local = Decimal("10800") # 90 shares * $120/share
    current_snapshot.cost_basis = Decimal("9000") # 90% of original cost

    # ACT
    new_record = PositionTimeseriesLogic.calculate_daily_record(
        current_snapshot=current_snapshot,
        previous_timeseries=previous_day_timeseries,
        bod_cashflow=bod_inflow,
        eod_cashflow=eod_inflow
    )

    # ASSERT
    assert new_record.bod_market_value == Decimal("11500") # Carried over from previous day
    assert new_record.bod_cashflow == bod_inflow
    assert new_record.eod_cashflow == eod_inflow
    assert new_record.eod_market_value == Decimal("10800")
    assert new_record.quantity == Decimal("90")
    assert new_record.cost == Decimal("100") # 9000 cost_basis / 90 quantity