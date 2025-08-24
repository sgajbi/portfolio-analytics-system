# tests/unit/services/recalculation_service/consumers/test_recalculation_consumer.py
import pytest
from unittest.mock import MagicMock, patch, AsyncMock, ANY
from datetime import date
import asyncio
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession
from portfolio_common.database_models import RecalculationJob
from src.services.recalculation_service.app.consumers.recalculation_consumer import RecalculationJobConsumer
from src.services.recalculation_service.app.repositories.recalculation_repository import RecalculationRepository, CoalescedRecalculationJob

pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_dependencies():
    """A fixture to patch all external dependencies for the consumer test."""
    mock_repo = AsyncMock(spec=RecalculationRepository)
    
    mock_db_session = AsyncMock(spec=AsyncSession)
    
    @asynccontextmanager
    async def mock_begin_transaction():
        yield

    mock_db_session.begin.side_effect = mock_begin_transaction
    
    async def get_session_gen():
        yield mock_db_session

    with patch(
        "src.services.recalculation_service.app.consumers.recalculation_consumer.get_async_db_session", new=get_session_gen
    ), patch(
        "src.services.recalculation_service.app.consumers.recalculation_consumer.RecalculationRepository", return_value=mock_repo
    ), patch(
        "src.services.recalculation_service.app.consumers.recalculation_consumer.RecalculationLogic.execute"
    ) as mock_logic_execute:
        yield {
            "repo": mock_repo,
            "logic_execute": mock_logic_execute
        }

async def test_consumer_claims_and_executes_coalesced_job(mock_dependencies):
    """
    GIVEN multiple pending jobs for a security
    WHEN the consumer's run loop executes
    THEN it should claim all jobs, call logic with the earliest date, and mark all jobs as COMPLETE.
    """
    # ARRANGE
    mock_repo = mock_dependencies["repo"]
    mock_logic_execute = mock_dependencies["logic_execute"]
    
    job1 = RecalculationJob(id=1, portfolio_id="P1", security_id="S1", from_date=date(2025, 8, 10), correlation_id="corr-1")
    job2 = RecalculationJob(id=2, portfolio_id="P1", security_id="S1", from_date=date(2025, 8, 5), correlation_id="corr-2")
    coalesced_job_to_process = CoalescedRecalculationJob(
        earliest_from_date=date(2025, 8, 5),
        claimed_jobs=[job1, job2]
    )
    
    consumer = RecalculationJobConsumer(poll_interval=0.01)

    async def find_and_stop(*args, **kwargs):
        consumer.stop()
        return coalesced_job_to_process
    mock_repo.find_and_claim_coalesced_job.side_effect = find_and_stop

    # ACT
    await consumer.run()

    # ASSERT
    mock_repo.find_and_claim_coalesced_job.assert_awaited_once()
    mock_logic_execute.assert_awaited_once_with(
        db_session=ANY,
        job_id=job1.id,
        portfolio_id=job1.portfolio_id,
        security_id=job1.security_id,
        from_date=coalesced_job_to_process.earliest_from_date,
        correlation_id=job1.correlation_id
    )
    mock_repo.update_job_status.assert_awaited_once_with([1, 2], "COMPLETE")

async def test_consumer_marks_job_as_failed_on_logic_error(mock_dependencies):
    """
    GIVEN a coalesced job that causes an error during recalculation logic
    WHEN the consumer processes it
    THEN it should mark all claimed jobs as FAILED.
    """
    # ARRANGE
    mock_repo = mock_dependencies["repo"]
    mock_logic_execute = mock_dependencies["logic_execute"]

    jobs = [RecalculationJob(id=5, portfolio_id="P_FAIL", security_id="S_FAIL", from_date=date(2025, 1, 1))]
    coalesced_job_to_process = CoalescedRecalculationJob(earliest_from_date=date(2025, 1, 1), claimed_jobs=jobs)
    
    mock_logic_execute.side_effect = ValueError("Simulated logic failure")
    
    consumer = RecalculationJobConsumer(poll_interval=0.01)
    
    async def find_and_stop(*args, **kwargs):
        consumer.stop()
        return coalesced_job_to_process
    mock_repo.find_and_claim_coalesced_job.side_effect = find_and_stop

    # ACT
    await consumer.run()

    # ASSERT
    mock_repo.find_and_claim_coalesced_job.assert_awaited_once()
    mock_logic_execute.assert_awaited_once()
    mock_repo.update_job_status.assert_awaited_once_with([5], "FAILED")

async def test_consumer_does_nothing_when_no_jobs(mock_dependencies):
    """
    GIVEN no pending jobs in the database
    WHEN the consumer's run loop executes
    THEN it should not call any processing logic or update statuses.
    """
    # ARRANGE
    mock_repo = mock_dependencies["repo"]
    mock_logic_execute = mock_dependencies["logic_execute"]

    consumer = RecalculationJobConsumer(poll_interval=0.01)

    async def find_and_stop(*args, **kwargs):
        consumer.stop()
        return None # Simulate no jobs found
    mock_repo.find_and_claim_coalesced_job.side_effect = find_and_stop

    # ACT
    await consumer.run()

    # ASSERT
    mock_repo.find_and_claim_coalesced_job.assert_awaited_once()
    mock_logic_execute.assert_not_called()
    mock_repo.update_job_status.assert_not_called()