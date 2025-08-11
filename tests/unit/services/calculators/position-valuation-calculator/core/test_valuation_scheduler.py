# tests/unit/services/calculators/position-valuation-calculator/core/test_valuation_scheduler.py
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import date

from portfolio_common.database_models import PortfolioValuationJob
from portfolio_common.kafka_utils import KafkaProducer
from portfolio_common.config import KAFKA_VALUATION_REQUIRED_TOPIC
from services.calculators.position_valuation_calculator.app.core.valuation_scheduler import ValuationScheduler
from services.calculators.position_valuation_calculator.app.repositories.valuation_repository import ValuationRepository

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
        PortfolioValuationJob(id=1, portfolio_id="PORT_01", security_id="SEC_01", valuation_date=date(2025, 8, 10)),
        PortfolioValuationJob(id=2, portfolio_id="PORT_02", security_id="SEC_02", valuation_date=date(2025, 8, 11)),
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