# tests/unit/services/calculators/position-valuation-calculator/repositories/test_valuation_repository.py
import pytest
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from portfolio_common.database_models import Portfolio, DailyPositionSnapshot, PositionState, BusinessDate
from src.services.calculators.position_valuation_calculator.app.repositories.valuation_repository import ValuationRepository

pytestmark = pytest.mark.asyncio

@pytest.fixture(scope="function")
def setup_holdings_data(db_engine, clean_db):
    """
    Sets up position snapshots for testing the holding lookup.
    - P1 holds S1 on the target date.
    - P2 sold S1 before the target date.
    - P3 holds S1, but the last snapshot is after the target date (should not be found).
    - P4 holds a different security, S2.
    """
    with Session(db_engine) as session:
        session.add_all([
            Portfolio(portfolio_id="P1", base_currency="USD", open_date=date(2024,1,1), risk_exposure="a", investment_time_horizon="b", portfolio_type="c", booking_center="d", cif_id="e", status="f"),
            Portfolio(portfolio_id="P2", base_currency="USD", open_date=date(2024,1,1), risk_exposure="a", investment_time_horizon="b", portfolio_type="c", booking_center="d", cif_id="e", status="f"),
            Portfolio(portfolio_id="P3", base_currency="USD", open_date=date(2024,1,1), risk_exposure="a", investment_time_horizon="b", portfolio_type="c", booking_center="d", cif_id="e", status="f"),
            Portfolio(portfolio_id="P4", base_currency="USD", open_date=date(2024,1,1), risk_exposure="a", investment_time_horizon="b", portfolio_type="c", booking_center="d", cif_id="e", status="f"),
        ])
        session.flush()

        snapshots = [
            # P1: Has a position before the date
            DailyPositionSnapshot(portfolio_id="P1", security_id="S1", date=date(2025, 8, 5), quantity=Decimal("100"), cost_basis=Decimal("1")),
            # P2: Sold position before the date
            DailyPositionSnapshot(portfolio_id="P2", security_id="S1", date=date(2025, 8, 4), quantity=Decimal("100"), cost_basis=Decimal("1")),
            DailyPositionSnapshot(portfolio_id="P2", security_id="S1", date=date(2025, 8, 6), quantity=Decimal("0"), cost_basis=Decimal("0")),
            # P3: Snapshot is after the target date
            DailyPositionSnapshot(portfolio_id="P3", security_id="S1", date=date(2025, 8, 15), quantity=Decimal("100"), cost_basis=Decimal("1")),
            # P4: Holds a different security
            DailyPositionSnapshot(portfolio_id="P4", security_id="S2", date=date(2025, 8, 5), quantity=Decimal("100"), cost_basis=Decimal("1")),
        ]
        session.add_all(snapshots)
        session.commit()

async def test_find_portfolios_holding_security_on_date(db_engine, setup_holdings_data, async_db_session: AsyncSession):
    """
    GIVEN a set of portfolios with various position histories for security 'S1'
    WHEN find_portfolios_holding_security_on_date is called for 'S1' on a specific date
    THEN it should only return the portfolio that had a non-zero position on or before that date.
    """
    # ARRANGE
    repo = ValuationRepository(async_db_session)
    target_date = date(2025, 8, 10)
    target_security = "S1"

    # ACT
    portfolio_ids = await repo.find_portfolios_holding_security_on_date(target_security, target_date)

    # ASSERT
    assert len(portfolio_ids) == 1
    assert portfolio_ids[0] == "P1"

async def test_find_contiguous_snapshot_dates(db_engine, clean_db, async_db_session: AsyncSession):
    """
    GIVEN position states and snapshots with and without gaps
    WHEN find_contiguous_snapshot_dates is called
    THEN it should return the correct latest contiguous date for each key.
    """
    # ARRANGE
    repo = ValuationRepository(async_db_session)
    states = [
        PositionState(portfolio_id="P1", security_id="S1", watermark_date=date(2025, 8, 1), epoch=1, status='REPROCESSING'), # Has a gap
        PositionState(portfolio_id="P2", security_id="S2", watermark_date=date(2025, 8, 1), epoch=1, status='REPROCESSING'), # No gaps
        PositionState(portfolio_id="P3", security_id="S3", watermark_date=date(2025, 8, 1), epoch=1, status='REPROCESSING'), # No new snapshots
    ]
    snapshots = [
        # P1/S1: Snapshots for day 2 and 4, but missing day 3 (gap)
        DailyPositionSnapshot(portfolio_id="P1", security_id="S1", date=date(2025, 8, 2), epoch=1, quantity=1, cost_basis=1),
        DailyPositionSnapshot(portfolio_id="P1", security_id="S1", date=date(2025, 8, 4), epoch=1, quantity=1, cost_basis=1),
        # P2/S2: Snapshots for days 2, 3, 4 (contiguous)
        DailyPositionSnapshot(portfolio_id="P2", security_id="S2", date=date(2025, 8, 2), epoch=1, quantity=1, cost_basis=1),
        DailyPositionSnapshot(portfolio_id="P2", security_id="S2", date=date(2025, 8, 3), epoch=1, quantity=1, cost_basis=1),
        DailyPositionSnapshot(portfolio_id="P2", security_id="S2", date=date(2025, 8, 4), epoch=1, quantity=1, cost_basis=1),
    ]
    business_dates = [BusinessDate(date=d) for d in [date(2025, 8, 2), date(2025, 8, 3), date(2025, 8, 4)]]
    
    async_db_session.add_all(states + snapshots + business_dates)
    await async_db_session.commit()

    # ACT
    advancable_dates = await repo.find_contiguous_snapshot_dates(states)

    # ASSERT
    assert len(advancable_dates) == 2
    assert advancable_dates[("P1", "S1")] == date(2025, 8, 2) # Stops at the gap
    assert advancable_dates[("P2", "S2")] == date(2025, 8, 4) # Advances to the end
    assert ("P3", "S3") not in advancable_dates # No snapshots, so not in result