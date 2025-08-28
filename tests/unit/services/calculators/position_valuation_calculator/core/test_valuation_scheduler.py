# tests/unit/services/calculators/position-valuation-calculator/core/test_valuation_scheduler.py
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import date, timedelta
import asyncio

from sqlalchemy.ext.asyncio import AsyncSession
from portfolio_common.database_models import PortfolioValuationJob, PositionState
from portfolio_common.kafka_utils import KafkaProducer
from portfolio_common.config import KAFKA_VALUATION_REQUIRED_TOPIC
from services.calculators.position_valuation_calculator.app.core.valuation_scheduler import ValuationScheduler
from services.calculators.position_valuation_calculator.app.repositories.valuation_repository import ValuationRepository
from portfolio_common.valuation_job_repository import ValuationJobRepository
from portfolio_common.position_state_repository import PositionStateRepository

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
    mock_state_repo = AsyncMock(spec=PositionStateRepository)
    
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
    ), patch(
        "services.calculators.position_valuation_calculator.app.core.valuation_scheduler.PositionStateRepository", return_value=mock_state_repo
    ):
        yield {
            "repo": mock_repo,
            "job_repo": mock_job_repo,
            "state_repo": mock_state_repo
        }

async def test_scheduler_creates_position_aware_backfill_jobs(scheduler: ValuationScheduler, mock_dependencies: dict):
    """
    GIVEN a state with a very old watermark but a much more recent first_open_date
    WHEN the scheduler runs _create_backfill_jobs
    THEN it should create jobs starting from the first_open_date, not the watermark.
    """
    # ARRANGE
    mock_repo = mock_dependencies["repo"]
    mock_job_repo = mock_dependencies["job_repo"]
    
    latest_business_date = date(2025, 8, 12)
    first_open_date = date(2025, 8, 10)

    states_to_backfill = [
        PositionState(portfolio_id="P1", security_id="S1", watermark_date=date(1970, 1, 1), epoch=1)
    ]
    
    mock_repo.get_latest_business_date.return_value = latest_business_date
    mock_repo.get_states_needing_backfill.return_value = states_to_backfill
    mock_repo.get_first_open_dates_for_keys.return_value = {
        ("P1", "S1", 1): first_open_date
    }

    # ACT
    await scheduler._create_backfill_jobs(AsyncMock())

    # ASSERT
    # It should create jobs for the 10th, 11th, and 12th
    assert mock_job_repo.upsert_job.call_count == 3
    
    # Check that the first job created is for the first_open_date
    first_call_args = mock_job_repo.upsert_job.call_args_list[0].kwargs
    assert first_call_args['valuation_date'] == date(2025, 8, 10)
    assert first_call_args['epoch'] == 1

async def test_scheduler_skips_jobs_for_keys_with_no_position_history(scheduler: ValuationScheduler, mock_dependencies: dict):
    """
    GIVEN a state needing backfill but no corresponding position history
    WHEN the scheduler runs _create_backfill_jobs
    THEN it should NOT create any valuation jobs for that key.
    """
    # ARRANGE
    mock_repo = mock_dependencies["repo"]
    mock_job_repo = mock_dependencies["job_repo"]
    
    latest_business_date = date(2025, 8, 12)
    states_to_backfill = [
        PositionState(portfolio_id="P1", security_id="S1", watermark_date=date(2025, 8, 10), epoch=1)
    ]
    
    mock_repo.get_latest_business_date.return_value = latest_business_date
    mock_repo.get_states_needing_backfill.return_value = states_to_backfill
    # Simulate the key not being found in the position history
    mock_repo.get_first_open_dates_for_keys.return_value = {}

    # ACT
    await scheduler._create_backfill_jobs(AsyncMock())

    # ASSERT
    mock_job_repo.upsert_job.assert_not_called()

# --- NEW TEST ---
async def test_scheduler_advances_watermarks(scheduler: ValuationScheduler, mock_dependencies: dict):
    """
    GIVEN reprocessing states that have new contiguous snapshots
    WHEN the scheduler's _advance_watermarks logic runs
    THEN it should bulk update the states correctly.
    """
    # ARRANGE
    mock_repo = mock_dependencies["repo"]
    mock_state_repo = mock_dependencies["state_repo"]
    latest_business_date = date(2025, 8, 15)

    # --- FIX: Explicitly set the 'status' for each test object ---
    lagging_states = [
        # This one is now complete
        PositionState(portfolio_id="P1", security_id="S1", watermark_date=date(2025, 8, 10), epoch=1, status='REPROCESSING'),
        # This one has advanced but is not yet complete
        PositionState(portfolio_id="P2", security_id="S2", watermark_date=date(2025, 8, 10), epoch=2, status='REPROCESSING'),
        # This one has no new snapshots, so it won't be in the result
        PositionState(portfolio_id="P3", security_id="S3", watermark_date=date(2025, 8, 10), epoch=1, status='REPROCESSING'),
    ]
    advancable_dates = {
        ("P1", "S1"): date(2025, 8, 15), # Complete
        ("P2", "S2"): date(2025, 8, 12), # Partially advanced
    }

    mock_repo.get_latest_business_date.return_value = latest_business_date
    mock_repo.get_lagging_states.return_value = lagging_states
    mock_repo.find_contiguous_snapshot_dates.return_value = advancable_dates

    # ACT
    await scheduler._advance_watermarks(AsyncMock())

    # ASSERT
    mock_state_repo.bulk_update_states.assert_awaited_once()
    updates_arg = mock_state_repo.bulk_update_states.call_args[0][0]
    
    assert len(updates_arg) == 2
    
    update1 = next(u for u in updates_arg if u['portfolio_id'] == 'P1')
    assert update1['watermark_date'] == date(2025, 8, 15)
    assert update1['status'] == 'CURRENT'

    update2 = next(u for u in updates_arg if u['portfolio_id'] == 'P2')
    assert update2['watermark_date'] == date(2025, 8, 12)
    assert update2['status'] == 'REPROCESSING'