# tests/unit/services/recalculation_service/repositories/test_recalculation_repository.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from sqlalchemy import text, select
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.expression import delete, update, Select, Update, Delete, TextClause
from sqlalchemy.dialects import postgresql

from portfolio_common.database_models import (
    RecalculationJob,
    Transaction,
    PositionHistory,
    DailyPositionSnapshot,
    PositionTimeseries,
    PortfolioTimeseries,
    Cashflow
)
from src.services.recalculation_service.app.repositories.recalculation_repository import RecalculationRepository

pytestmark = pytest.mark.asyncio

@pytest.fixture(scope="function")
def setup_coalescing_jobs(db_engine, clean_db):
    """
    Sets up a set of jobs to test coalescing logic:
    - Two PENDING jobs for (P1, S1) with different dates.
    - One PENDING job for (P2, S2) which should not be picked.
    - One PROCESSING job for (P1, S1) which should be ignored (skip locked).
    """
    with Session(db_engine) as session:
        session.add_all([
            RecalculationJob(portfolio_id="P1", security_id="S1", from_date=date(2025, 8, 10), status="PENDING", created_at=datetime(2025, 8, 11)),
            RecalculationJob(portfolio_id="P1", security_id="S1", from_date=date(2025, 8, 5), status="PENDING", created_at=datetime(2025, 8, 10)),
            RecalculationJob(portfolio_id="P2", security_id="S2", from_date=date(2025, 8, 1), status="PENDING"),
            RecalculationJob(portfolio_id="P1", security_id="S1", from_date=date(2025, 8, 1), status="PROCESSING"),
        ])
        session.commit()

async def test_find_and_claim_coalesced_job(db_engine, clean_db, setup_coalescing_jobs, async_db_session: AsyncSession):
    """
    GIVEN multiple pending jobs for the same security
    WHEN find_and_claim_coalesced_job is called
    THEN it should claim all jobs for that security and return the earliest date.
    """
    # ARRANGE
    repo = RecalculationRepository(async_db_session)
    
    # ACT
    coalesced_job = await repo.find_and_claim_coalesced_job()
    await async_db_session.commit()

    # ASSERT
    assert coalesced_job is not None
    assert len(coalesced_job.claimed_jobs) == 2
    assert coalesced_job.earliest_from_date == date(2025, 8, 5)
    
    # Verify the database state
    with Session(db_engine) as session:
        processing_count = session.query(RecalculationJob).filter_by(portfolio_id="P1", security_id="S1", status="PROCESSING").count()
        pending_count_p1 = session.query(RecalculationJob).filter_by(portfolio_id="P1", security_id="S1", status="PENDING").count()
        pending_count_p2 = session.query(RecalculationJob).filter_by(portfolio_id="P2", security_id="S2", status="PENDING").count()
        
        # The original PROCESSING job + the 2 newly claimed ones
        assert processing_count == 3
        assert pending_count_p1 == 0
        assert pending_count_p2 == 1 # The job for P2 should be untouched

async def test_update_job_status_multiple_ids(db_engine, clean_db, setup_coalescing_jobs, async_db_session: AsyncSession):
    """
    GIVEN a list of job IDs
    WHEN update_job_status is called
    THEN it should update all specified jobs to the new status.
    """
    # ARRANGE
    repo = RecalculationRepository(async_db_session)
    job_ids_to_update = [1, 2] # Corresponds to the two PENDING jobs for P1, S1

    # ACT
    await repo.update_job_status(job_ids=job_ids_to_update, status="COMPLETE")
    await async_db_session.commit()

    # ASSERT
    with Session(db_engine) as session:
        completed_jobs = session.query(RecalculationJob).filter(RecalculationJob.id.in_(job_ids_to_update)).all()
        assert len(completed_jobs) == 2
        assert all(job.status == "COMPLETE" for job in completed_jobs)