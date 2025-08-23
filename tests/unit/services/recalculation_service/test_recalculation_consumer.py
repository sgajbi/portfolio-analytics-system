# tests/unit/services/recalculation_service/test_recalculation_consumer.py
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import date
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession
from portfolio_common.database_models import RecalculationJob
from src.services.recalculation_service.app.consumers.recalculation_consumer import RecalculationJobConsumer
from src.services.recalculation_service.app.repositories.recalculation_repository import RecalculationRepository

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

async def test_consumer_claims_and_executes_job(mock_dependencies):
    """
    GIVEN a pending job in the database
    WHEN the consumer's run loop executes
    THEN it should claim the job, call the recalculation logic, and mark the job as COMPLETE.
    """
    # ARRANGE
    mock_repo = mock_dependencies["repo"]
    mock_logic_execute = mock_dependencies["logic_execute"]
    
    job_to_process = RecalculationJob(
        id=1, portfolio_id="P1", security_id="S1", from_date=date(2025, 1, 1), status="PENDING"
    )
    mock_repo.find_and_claim_job.return_value = job_to_process
    
    consumer = RecalculationJobConsumer(poll_interval=0.01)

    # ACT: Run the consumer for a very short period to ensure it completes one cycle
    run_task = asyncio.create_task(consumer.run())
    await asyncio.sleep(0.1)
    consumer.stop()
    await run_task

    # ASSERT
    mock_repo.find_and_claim_job.assert_awaited_once()
    mock_logic_execute.assert_awaited_once_with(
        db_session=ANY,
        portfolio_id="P1",
        security_id="S1",
        from_date=date(2025, 1, 1)
    )
    mock_repo.update_job_status.assert_awaited_once_with(1, "COMPLETE")