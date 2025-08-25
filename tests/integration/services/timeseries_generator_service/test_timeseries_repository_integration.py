# tests/integration/services/timeseries_generator_service/test_timeseries_repository_integration.py
import pytest
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
# --- UPDATED IMPORTS ---
from portfolio_common.database_models import Portfolio, PortfolioAggregationJob, PortfolioTimeseries, PositionState
from src.services.timeseries_generator_service.app.repositories.timeseries_repository import TimeseriesRepository

pytestmark = pytest.mark.asyncio

@pytest.fixture(scope="function")
def setup_sequential_jobs(db_engine, clean_db):
    """
    Sets up a portfolio and two sequential, PENDING aggregation jobs.
    Also creates the necessary PositionState record for epoch awareness.
    """
    portfolio_id = "SEQ_JOB_TEST_01"
    day1 = date(2025, 8, 18)
    day2 = date(2025, 8, 19)

    with Session(db_engine) as session:
        session.add(Portfolio(portfolio_id=portfolio_id, base_currency="USD", open_date=date(2024,1,1), risk_exposure="a", investment_time_horizon="b", portfolio_type="c", booking_center="d", cif_id="e", status="f"))
        
        # --- NEW: Add PositionState record for the portfolio ---
        # The scheduler logic now depends on this to determine the correct epoch.
        # We assume no securities yet, so it's a placeholder for the portfolio's max epoch.
        # Note: A real flow would create this when a security is first traded.
        # For this test, we can just ensure a record exists for the portfolio.
        # A better approach for a real system might be to have a portfolio-level epoch,
        # but for now, this aligns the test with the query's expectation.
        # Let's assume the scheduler logic needs a baseline. A "placeholder" security is okay here.
        session.add(PositionState(
            portfolio_id=portfolio_id, 
            security_id="PLACEHOLDER", 
            epoch=0, 
            watermark_date=date(2024,1,1))
        )
        
        session.flush()

        session.add_all([
            PortfolioAggregationJob(portfolio_id=portfolio_id, aggregation_date=day1, status="PENDING"),
            PortfolioAggregationJob(portfolio_id=portfolio_id, aggregation_date=day2, status="PENDING"),
        ])
        session.commit()
    
    return {"portfolio_id": portfolio_id, "day1": day1, "day2": day2}


async def test_find_and_claim_eligible_jobs_sequential_logic(setup_sequential_jobs, async_db_session: AsyncSession, db_engine):
    """
    GIVEN two sequential PENDING jobs for Day 1 and Day 2
    WHEN find_and_claim_eligible_jobs is called
    THEN it should only claim the first job (Day 1).
    WHEN a timeseries record is created for Day 1
    THEN a subsequent call should claim the job for Day 2.
    """
    # ARRANGE
    repo = TimeseriesRepository(async_db_session)
    portfolio_id = setup_sequential_jobs["portfolio_id"]
    day1 = setup_sequential_jobs["day1"]
    day2 = setup_sequential_jobs["day2"]

    # ACT 1: First call
    claimed_jobs_1 = await repo.find_and_claim_eligible_jobs(batch_size=5)
    await async_db_session.commit()

    # ASSERT 1: Should only claim the first job
    assert len(claimed_jobs_1) == 1
    assert claimed_jobs_1[0].aggregation_date == day1

    # ARRANGE 2: Simulate the completion of the first job by creating its timeseries record
    with Session(db_engine) as session:
        # --- UPDATED: Explicitly set epoch to match what the query expects (0) ---
        session.add(PortfolioTimeseries(
            portfolio_id=portfolio_id, 
            date=day1, 
            epoch=0, # The default/initial epoch
            bod_market_value=0, 
            bod_cashflow=0, 
            eod_cashflow=0, 
            eod_market_value=0, 
            fees=0
        ))
        session.commit()
    
    # ACT 2: Second call
    claimed_jobs_2 = await repo.find_and_claim_eligible_jobs(batch_size=5)
    await async_db_session.commit()
    
    # ASSERT 2: Should now claim the second job
    assert len(claimed_jobs_2) == 1
    assert claimed_jobs_2[0].aggregation_date == day2