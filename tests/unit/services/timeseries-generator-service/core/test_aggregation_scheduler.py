# tests/unit/services/timeseries-generator-service/core/test_aggregation_scheduler.py
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import date

from portfolio_common.database_models import PortfolioAggregationJob
from portfolio_common.kafka_utils import KafkaProducer
from services.timeseries_generator_service.app.core.aggregation_scheduler import AggregationScheduler

pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_kafka_producer() -> MagicMock:
    """Provides a mock KafkaProducer."""
    return MagicMock(spec=KafkaProducer)

@pytest.fixture
def scheduler(mock_kafka_producer: MagicMock) -> AggregationScheduler:
    """Provides an AggregationScheduler instance with a mocked producer."""
    with patch(
        "services.timeseries_generator_service.app.core.aggregation_scheduler.get_kafka_producer",
        return_value=mock_kafka_producer
    ):
        return AggregationScheduler(poll_interval=0.1)

async def test_scheduler_dispatches_eligible_jobs(scheduler: AggregationScheduler, mock_kafka_producer: MagicMock):
    """
    GIVEN a set of pending aggregation jobs in the database
    WHEN the scheduler's main loop runs
    THEN it should claim the jobs and dispatch them as Kafka events.
    """
    # ARRANGE
    mock_db_session = AsyncMock()
    mock_db_session.begin.return_value = AsyncMock() # For the async context manager
    async def get_db_session_gen():
        yield mock_db_session
        
    mock_repo = AsyncMock()
    
    # Simulate the repository finding and claiming two eligible jobs
    claimed_jobs = [
        PortfolioAggregationJob(id=1, portfolio_id="PORT_01", aggregation_date=date(2025, 8, 10)),
        PortfolioAggregationJob(id=2, portfolio_id="PORT_02", aggregation_date=date(2025, 8, 10)),
    ]
    mock_repo.find_and_claim_eligible_jobs.return_value = claimed_jobs

    with patch(
        "services.timeseries_generator_service.app.core.aggregation_scheduler.get_async_db_session", new=get_db_session_gen
    ), patch(
        "services.timeseries_generator_service.app.core.aggregation_scheduler.TimeseriesRepository", return_value=mock_repo
    ):
        # ACT
        # Run a single cycle of the scheduler's logic by calling its internal method
        await scheduler._dispatch_jobs(claimed_jobs)

    # ASSERT
    # 1. Verify the producer was called to publish a message for each job
    assert mock_kafka_producer.publish_message.call_count == 2
    mock_kafka_producer.flush.assert_called_once()

    # 2. Inspect the first call to ensure it's correct
    first_call_args = mock_kafka_producer.publish_message.call_args_list[0].kwargs
    assert first_call_args['topic'] == "portfolio_aggregation_required"
    assert first_call_args['key'] == "PORT_01"
    assert first_call_args['value']['portfolio_id'] == "PORT_01"
    assert first_call_args['value']['aggregation_date'] == "2025-08-10"

    # 3. Inspect the second call
    second_call_args = mock_kafka_producer.publish_message.call_args_list[1].kwargs
    assert second_call_args['key'] == "PORT_02"