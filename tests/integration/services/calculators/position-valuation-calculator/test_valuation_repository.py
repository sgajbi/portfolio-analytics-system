# tests/integration/services/calculators/position-valuation-calculator/test_valuation_repository.py
import pytest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from portfolio_common.database_models import PortfolioValuationJob, DailyPositionSnapshot, Portfolio
from src.services.calculators.position_valuation_calculator.app.repositories.valuation_repository import ValuationRepository

pytestmark = pytest.mark.asyncio

@pytest.fixture(scope="function")
def setup_stale_job_data(db_engine):
    """
    Sets up a variety of valuation jobs in the database:
    - One recent 'PROCESSING' job (should not be reset).
    - One stale 'PROCESSING' job (should be reset).
    - One stale 'PENDING' job (should not be reset).
    - One stale 'COMPLETE' job (should not be reset).
    """
    with Session(db_engine) as session:
        now = datetime.now(timezone.utc)
        stale_time = now - timedelta(minutes=30)
        
        jobs = [
            # 1. Stale and PROCESSING -> Should be reset to PENDING
            PortfolioValuationJob(portfolio_id="P1", security_id="S1", valuation_date=date(2025, 8, 1), status="PROCESSING", updated_at=stale_time),
            # 2. Recent and PROCESSING -> Should NOT be touched
            PortfolioValuationJob(portfolio_id="P2", security_id="S2", valuation_date=date(2025, 8, 1), status="PROCESSING", updated_at=now),
            # 3. Stale and PENDING -> Should NOT be touched
            PortfolioValuationJob(portfolio_id="P3", security_id="S3", valuation_date=date(2025, 8, 1), status="PENDING", updated_at=stale_time),
            # 4. Stale and COMPLETE -> Should NOT be touched
            PortfolioValuationJob(portfolio_id="P4", security_id="S4", valuation_date=date(2025, 8, 1), status="COMPLETE", updated_at=stale_time),
        ]
        session.add_all(jobs)
        session.commit()

@pytest.fixture(scope="function")
def setup_holdings_data(db_engine):
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

async def test_find_portfolios_holding_security_on_date(db_engine, clean_db, setup_holdings_data, async_db_session: AsyncSession):
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

async def test_find_and_reset_stale_jobs(db_engine, clean_db, setup_stale_job_data, async_db_session: AsyncSession):
    """
    GIVEN a mix of recent and stale jobs in various states
    WHEN find_and_reset_stale_jobs is called
    THEN it should only reset the single stale 'PROCESSING' job to 'PENDING'
    AND return a count of 1.
    """
    # ARRANGE
    repo = ValuationRepository(async_db_session)
    
    # ACT
    reset_count = await repo.find_and_reset_stale_jobs(timeout_minutes=15)
    await async_db_session.commit()

    # ASSERT
    assert reset_count == 1
    
    with Session(db_engine) as session:
        # Verify the stale PROCESSING job was reset
        job1 = session.query(PortfolioValuationJob).filter_by(portfolio_id="P1").one()
        assert job1.status == "PENDING"
        
        # Verify the other jobs were untouched
        job2 = session.query(PortfolioValuationJob).filter_by(portfolio_id="P2").one()
        assert job2.status == "PROCESSING"
        
        job3 = session.query(PortfolioValuationJob).filter_by(portfolio_id="P3").one()
        assert job3.status == "PENDING"
        
        job4 = session.query(PortfolioValuationJob).filter_by(portfolio_id="P4").one()
        assert job4.status == "COMPLETE"