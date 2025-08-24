# tests/unit/services/calculators/position-valuation-calculator/core/test_valuation_scheduler.py
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import date, timedelta
import asyncio
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession
from portfolio_common.database_models import PortfolioValuationJob
from portfolio_common.kafka_utils import KafkaProducer
from portfolio_common.config import KAFKA_VALUATION_REQUIRED_TOPIC
from services.calculators.position_valuation_calculator.app.core.valuation_scheduler import ValuationScheduler
from services.calculators.position_valuation_calculator.app.repositories.valuation_repository import ValuationRepository
from portfolio_common.valuation_job_repository import ValuationJobRepository

pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_kafka_producer() -> MagicMock:
    """Provides a mock KafkaProducer."""
    return MagicMock(spec=KafkaProducer)

@pytest.fixture
def scheduler(mock_kafka_producer: MagicMock) -> ValuationScheduler:
    """Provides a ValuationScheduler instance with a mocked producer."""
    with patch(
        "services.calculators.position_valuation_calculator.app.core.valuation_scheduler.get_kafka_producer",
        return_value=mock_kafka_producer
    ):
        return ValuationScheduler(poll_interval=0.1)

@pytest.fixture
def mock_dependencies():
    """A fixture to patch all external dependencies for the scheduler test."""
    mock_repo = AsyncMock(spec=ValuationRepository)
    mock_job_repo = AsyncMock(spec=ValuationJobRepository)
    
    mock_db_session = AsyncMock(spec=AsyncSession)
    mock_transaction = AsyncMock()
    mock_db_session.begin.return_value = mock_transaction
    
    async def get_session_gen():
        yield mock_db_session

    with patch(
        "services.calculators.position_valuation_calculator.app.core.valuation_scheduler.get_async_db_session", new=get_session_gen
    ), patch(
        "services.calculators.position_valuation_calculator.app.core.valuation_scheduler.ValuationRepository", return_value=mock_repo
    ), patch(
        "services.calculators.position_valuation_calculator.app.core.valuation_scheduler.ValuationJobRepository", return_value=mock_job_repo
    ):
        yield {
            "repo": mock_repo,
            "job_repo": mock_job_repo
        }

async def test_scheduler_creates_roll_forward_jobs(scheduler: ValuationScheduler, mock_dependencies: dict):
    """
    GIVEN an open position whose last snapshot is two days old
    WHEN the scheduler's daily roll-forward logic runs
    THEN it should create two new valuation jobs for the missing days.
    """
    # ARRANGE
    mock_repo = mock_dependencies["repo"]
    mock_job_repo = mock_dependencies["job_repo"]
    
    latest_business_date = date(2025, 8, 12)
    last_snapshot_date = date(2025, 8, 10)

    mock_repo.get_latest_business_date.return_value = latest_business_date
    mock_repo.get_all_open_positions.return_value = [
        {'portfolio_id': 'P1', 'security_id': 'S1'}
    ]
    mock_repo.get_last_snapshot_date.return_value = last_snapshot_date
    mock_repo.are_recalculations_processing.return_value = [] # No locks

    # ACT
    # We call the internal method directly to test its logic in isolation
    await scheduler._create_daily_roll_forward_jobs(AsyncMock())

    # ASSERT
    # It should create jobs for the 11th and 12th
    assert mock_job_repo.upsert_job.call_count == 2
    
    call_dates = {call.kwargs['valuation_date'] for call in mock_job_repo.upsert_job.call_args_list}
    expected_dates = {date(2025, 8, 11), date(2025, 8, 12)}
    assert call_dates == expected_dates

async def test_scheduler_skips_locked_positions(scheduler: ValuationScheduler, mock_dependencies: dict):
    """
    GIVEN two open positions, one of which is locked by a recalculation job
    WHEN the scheduler's roll-forward logic runs
    THEN it should only create jobs for the unlocked position.
    """
    # ARRANGE
    mock_repo = mock_dependencies["repo"]
    mock_job_repo = mock_dependencies["job_repo"]

    mock_repo.get_latest_business_date.return_value = date(2025, 8, 12)
    mock_repo.get_all_open_positions.return_value = [
        {'portfolio_id': 'P1_LOCKED', 'security_id': 'S1_LOCKED'},
        {'portfolio_id': 'P2_UNLOCKED', 'security_id': 'S2_UNLOCKED'}
    ]
    # Simulate that P1/S1 is locked
    mock_repo.are_recalculations_processing.return_value = [("P1_LOCKED", "S1_LOCKED")]
    # Simulate both positions needing a roll-forward
    mock_repo.get_last_snapshot_date.return_value = date(2025, 8, 11)

    # ACT
    await scheduler._create_daily_roll_forward_jobs(AsyncMock())

    # ASSERT
    mock_repo.are_recalculations_processing.assert_awaited_once()
    
    # Assert that upsert_job was called only once, for the unlocked position
    mock_job_repo.upsert_job.assert_called_once()
    call_args = mock_job_repo.upsert_job.call_args.kwargs
    assert call_args['portfolio_id'] == 'P2_UNLOCKED'
    assert call_args['security_id'] == 'S2_UNLOCKED'
    assert call_args['valuation_date'] == date(2025, 8, 12)


async def test_scheduler_dispatches_eligible_jobs(scheduler: ValuationScheduler, mock_kafka_producer: MagicMock):
    """
    GIVEN a set of pending valuation jobs in the database
    WHEN the scheduler's main loop runs
    THEN it should claim the jobs and dispatch them as Kafka events.
    """
    # ARRANGE
    mock_db_session = AsyncMock()
    mock_db_session.begin.return_value = AsyncMock()
    
    async def get_db_session_gen():
        yield mock_db_session
        
    mock_repo = AsyncMock(spec=ValuationRepository)
    
    claimed_jobs = [
        PortfolioValuationJob(id=1, portfolio_id="PORT_01", security_id="SEC_01", valuation_date=date(2025, 8, 10), correlation_id="corr-1"),
        PortfolioValuationJob(id=2, portfolio_id="PORT_02", security_id="SEC_02", valuation_date=date(2025, 8, 11), correlation_id="corr-2"),
    ]
    mock_repo.find_and_claim_eligible_jobs.return_value = claimed_jobs

    with patch(
        "services.calculators.position_valuation_calculator.app.core.valuation_scheduler.get_async_db_session", new=get_db_session_gen
    ), patch(
        "services.calculators.position_valuation_calculator.app.core.valuation_scheduler.ValuationRepository", return_value=mock_repo
    ):
        # ACT: Run a single cycle of the scheduler's internal dispatch logic
        await scheduler._dispatch_jobs(claimed_jobs)

    # ASSERT
    # 1. Verify the producer was called for each job
    assert mock_kafka_producer.publish_message.call_count == 2
    mock_kafka_producer.flush.assert_called_once()

    # 2. Inspect the first call
    first_call_args = mock_kafka_producer.publish_message.call_args_list[0].kwargs
    assert first_call_args['topic'] == KAFKA_VALUATION_REQUIRED_TOPIC
    assert first_call_args['key'] == "PORT_01"
    assert first_call_args['value']['security_id'] == "SEC_01"
    assert first_call_args['value']['valuation_date'] == "2025-08-10"