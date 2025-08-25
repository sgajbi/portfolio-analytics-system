# tests/unit/services/calculators/position-valuation-calculator/core/test_valuation_scheduler.py
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import date, timedelta
import asyncio
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession
from portfolio_common.database_models import PortfolioValuationJob, PositionState
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

async def test_scheduler_creates_backfill_jobs(scheduler: ValuationScheduler, mock_dependencies: dict):
    """
    GIVEN a position_state with a watermark older than the latest business date
    WHEN the scheduler's _create_backfill_jobs logic runs
    THEN it should create valuation jobs for the missing days with the correct epoch.
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

    # ACT
    await scheduler._create_backfill_jobs(AsyncMock())

    # ASSERT
    # It should create jobs for the 11th and 12th
    assert mock_job_repo.upsert_job.call_count == 2
    
    # Check the call for the first missing day (the 11th)
    first_call_args = mock_job_repo.upsert_job.call_args_list[0].kwargs
    assert first_call_args['portfolio_id'] == 'P1'
    assert first_call_args['security_id'] == 'S1'
    assert first_call_args['valuation_date'] == date(2025, 8, 11)
    assert first_call_args['epoch'] == 1