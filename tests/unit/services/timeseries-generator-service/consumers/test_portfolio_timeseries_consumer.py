# tests/unit/services/timeseries-generator-service/consumers/test_portfolio_timeseries_consumer.py
import pytest
from unittest.mock import MagicMock, patch, AsyncMock, ANY
from datetime import date
from decimal import Decimal
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession
from portfolio_common.events import PortfolioAggregationRequiredEvent
from portfolio_common.database_models import (
    Portfolio, PositionTimeseries, Instrument, PortfolioTimeseries
)
from services.timeseries_generator_service.app.consumers.portfolio_timeseries_consumer import PortfolioTimeseriesConsumer
from services.timeseries_generator_service.app.repositories.timeseries_repository import TimeseriesRepository
from portfolio_common.outbox_repository import OutboxRepository

pytestmark = pytest.mark.asyncio

@pytest.fixture
def consumer() -> PortfolioTimeseriesConsumer:
    """Provides a clean instance of the PortfolioTimeseriesConsumer."""
    consumer = PortfolioTimeseriesConsumer(
        bootstrap_servers="mock_server",
        topic="portfolio_aggregation_required",
        group_id="test_group",
        dlq_topic="test.dlq"
    )
    consumer._send_to_dlq_async = AsyncMock()
    return consumer

@pytest.fixture
def mock_event() -> PortfolioAggregationRequiredEvent:
    """Provides a consistent aggregation event for tests."""
    return PortfolioAggregationRequiredEvent(
        portfolio_id="PORT_AGG_01",
        aggregation_date=date(2025, 8, 11)
    )

@pytest.fixture
def mock_kafka_message(mock_event: PortfolioAggregationRequiredEvent) -> MagicMock:
    """Creates a mock Kafka message from the event."""
    mock_msg = MagicMock()
    mock_msg.value.return_value = mock_event.model_dump_json().encode('utf-8')
    mock_msg.key.return_value = "test_key".encode('utf-8')
    mock_msg.headers.return_value = [('correlation_id', b'test-corr-id')]
    return mock_msg

@pytest.fixture
def mock_dependencies():
    """A fixture to patch all external dependencies for the consumer test."""
    mock_repo = AsyncMock(spec=TimeseriesRepository)
    mock_outbox_repo = AsyncMock(spec=OutboxRepository)
    
    mock_db_session = AsyncMock(spec=AsyncSession)
    mock_transaction = AsyncMock()
    mock_db_session.begin.return_value = mock_transaction
    
    async def get_session_gen():
        yield mock_db_session

    with patch(
        "services.timeseries_generator_service.app.consumers.portfolio_timeseries_consumer.get_async_db_session", new=get_session_gen
    ), patch(
        "services.timeseries_generator_service.app.consumers.portfolio_timeseries_consumer.TimeseriesRepository", return_value=mock_repo
    ), patch(
        "services.timeseries_generator_service.app.consumers.portfolio_timeseries_consumer.OutboxRepository", return_value=mock_outbox_repo
    ):
        yield {
            "repo": mock_repo,
            "outbox_repo": mock_outbox_repo
        }

async def test_process_message_success(
    consumer: PortfolioTimeseriesConsumer,
    mock_event: PortfolioAggregationRequiredEvent,
    mock_kafka_message: MagicMock,
    mock_dependencies: dict
):
    """
    GIVEN a portfolio aggregation event
    WHEN the message is processed successfully
    THEN it should aggregate data, save the new timeseries record, and update the job status to COMPLETE.
    """
    # ARRANGE
    mock_repo = mock_dependencies["repo"]
    mock_outbox_repo = mock_dependencies["outbox_repo"]
    
    mock_repo.get_portfolio.return_value = Portfolio(portfolio_id=mock_event.portfolio_id, base_currency="USD")
    mock_repo.get_all_position_timeseries_for_date.return_value = [
        PositionTimeseries(security_id="SEC_USD", date=mock_event.aggregation_date, eod_market_value=Decimal("1000"))
    ]
    mock_repo.get_portfolio_level_cashflows_for_date.return_value = []
    mock_repo.get_instruments_by_ids.return_value = [Instrument(security_id="SEC_USD", currency="USD")]
    mock_repo.get_last_portfolio_timeseries_before.return_value = None

    with patch.object(consumer, '_update_job_status', new_callable=AsyncMock) as mock_update_status:
        # ACT
        await consumer.process_message(mock_kafka_message)

        # ASSERT
        mock_repo.get_portfolio.assert_called_once_with(mock_event.portfolio_id)
        mock_repo.upsert_portfolio_timeseries.assert_called_once()
        mock_outbox_repo.create_outbox_event.assert_called_once()
        
        # FIX: Correctly assert the mock call including the db_session kwarg
        mock_update_status.assert_called_once_with(
            mock_event.portfolio_id,
            mock_event.aggregation_date,
            'COMPLETE',
            db_session=ANY
        )
        consumer._send_to_dlq_async.assert_not_called()