# tests/unit/services/calculators/position-valuation-calculator/core/test_valuation_scheduler.py
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import date, timedelta
import asyncio

from sqlalchemy.ext.asyncio import AsyncSession
from portfolio_common.database_models import PortfolioValuationJob, PositionState, InstrumentReprocessingState
from portfolio_common.kafka_utils import KafkaProducer
from portfolio_common.config import KAFKA_VALUATION_REQUIRED_TOPIC
from services.calculators.position_valuation_calculator.app.core.valuation_scheduler import ValuationScheduler
from services.calculators.position_valuation_calculator.app.repositories.valuation_repository import ValuationRepository
from portfolio_common.valuation_job_repository import ValuationJobRepository
from portfolio_common.position_state_repository import PositionStateRepository
from portfolio_common.reprocessing_job_repository import ReprocessingJobRepository
# --- NEW IMPORT ---
from portfolio_common.monitoring import INSTRUMENT_REPROCESSING_TRIGGERS_PENDING

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
    mock_repro_job_repo = AsyncMock(spec=ReprocessingJobRepository)
    
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
    ), patch( 
        "services.calculators.position_valuation_calculator.app.core.valuation_scheduler.ReprocessingJobRepository", return_value=mock_repro_job_repo
    ):
        yield {
            "repo": mock_repo,
            "job_repo": mock_job_repo,
            "state_repo": mock_state_repo,
            "repro_job_repo": mock_repro_job_repo
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

async def test_scheduler_dispatches_claimed_jobs(scheduler: ValuationScheduler, mock_kafka_producer: MagicMock):
    """
    GIVEN a list of claimed valuation jobs
    WHEN the scheduler's _dispatch_jobs logic runs
    THEN it should publish a correctly formed event for each job to Kafka.
    """
    # ARRANGE
    claimed_jobs = [
        PortfolioValuationJob(
            portfolio_id="P1", security_id="S1", valuation_date=date(2025, 8, 11), 
            epoch=1, correlation_id="corr-1"
        ),
        PortfolioValuationJob(
            portfolio_id="P2", security_id="S2", valuation_date=date(2025, 8, 12), 
            epoch=2, correlation_id="corr-2"
        ),
    ]

    # ACT
    await scheduler._dispatch_jobs(claimed_jobs)

    # ASSERT
    assert mock_kafka_producer.publish_message.call_count == 2
    mock_kafka_producer.flush.assert_called_once_with(timeout=10)

    # Inspect the first call to the producer
    first_call_args = mock_kafka_producer.publish_message.call_args_list[0].kwargs
    assert first_call_args['topic'] == KAFKA_VALUATION_REQUIRED_TOPIC
    assert first_call_args['key'] == "P1" # Keyed by portfolio_id
    
    # Verify payload content
    payload1 = first_call_args['value']
    assert payload1['portfolio_id'] == "P1"
    assert payload1['security_id'] == "S1"
    assert payload1['valuation_date'] == "2025-08-11"
    assert payload1['epoch'] == 1
    assert payload1['correlation_id'] == "corr-1"
    
    # Verify headers
    headers1 = dict(first_call_args['headers'])
    assert headers1['correlation_id'] == b'corr-1'

async def test_scheduler_creates_persistent_job_from_instrument_trigger(scheduler: ValuationScheduler, mock_dependencies: dict):
    """
    GIVEN an instrument reprocessing trigger in the database
    WHEN the scheduler runs _process_instrument_level_triggers
    THEN it should create a persistent job and NOT update watermarks directly.
    """
    # ARRANGE
    mock_repo = mock_dependencies["repo"]
    mock_repro_job_repo = mock_dependencies["repro_job_repo"]
    mock_state_repo = mock_dependencies["state_repo"]
    
    trigger_date = date(2025, 8, 5)
    triggers = [
        InstrumentReprocessingState(security_id="S1", earliest_impacted_date=trigger_date)
    ]
    
    mock_repo.get_instrument_reprocessing_triggers.return_value = triggers
    
    # ACT
    await scheduler._process_instrument_level_triggers(AsyncMock())

    # ASSERT
    # 1. Verify it checked for triggers
    mock_repo.get_instrument_reprocessing_triggers.assert_awaited_once()
    
    # 2. Verify it created a persistent job with the correct payload
    mock_repro_job_repo.create_job.assert_awaited_once()
    call_args = mock_repro_job_repo.create_job.call_args.kwargs
    assert call_args['job_type'] == 'RESET_WATERMARKS'
    assert call_args['payload'] == {
        "security_id": "S1",
        "earliest_impacted_date": "2025-08-05"
    }

    # 3. Verify it DID NOT call the old, direct fan-out logic
    mock_state_repo.update_watermarks_if_older.assert_not_called()
    mock_repo.find_portfolios_for_security.assert_not_called()
    
    # 4. Verify it consumed and deleted the original trigger
    mock_repo.delete_instrument_reprocessing_triggers.assert_awaited_once_with(["S1"])

@patch('src.services.calculators.position_valuation_calculator.app.core.valuation_scheduler.INSTRUMENT_REPROCESSING_TRIGGERS_PENDING')
async def test_scheduler_updates_pending_triggers_metric(mock_gauge, scheduler: ValuationScheduler, mock_dependencies: dict):
    """
    GIVEN a number of pending instrument reprocessing triggers
    WHEN the scheduler's _update_reprocessing_metrics logic runs
    THEN it should set the Prometheus gauge to the correct count.
    """
    # ARRANGE
    mock_repo = mock_dependencies["repo"]
    
    # Simulate the repository returning a count of 5 pending triggers
    mock_repo.get_instrument_reprocessing_triggers_count.return_value = 5
    
    # ACT
    await scheduler._update_reprocessing_metrics(AsyncMock())

    # ASSERT
    # Verify the repository was called to get the count
    mock_repo.get_instrument_reprocessing_triggers_count.assert_awaited_once()
    
    # Verify the Prometheus gauge's .set() method was called with the correct value
    mock_gauge.set.assert_called_once_with(5)