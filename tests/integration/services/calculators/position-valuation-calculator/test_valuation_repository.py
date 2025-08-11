# tests/integration/services/calculators/position-valuation-calculator/test_valuation_repository.py
import pytest
from datetime import date, datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import text

from portfolio_common.db import AsyncSessionLocal
from portfolio_common.database_models import PortfolioValuationJob
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
        now = datetime.utcnow()
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

async def test_find_and_reset_stale_jobs(db_engine, clean_db, setup_stale_job_data):
    """
    GIVEN a mix of recent and stale jobs in various states
    WHEN find_and_reset_stale_jobs is called
    THEN it should only reset the single stale 'PROCESSING' job to 'PENDING'
    AND return a count of 1.
    """
    # ARRANGE
    async with AsyncSessionLocal() as session:
        repo = ValuationRepository(session)
        
        # ACT
        reset_count = await repo.find_and_reset_stale_jobs(timeout_minutes=15)
        await session.commit()

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