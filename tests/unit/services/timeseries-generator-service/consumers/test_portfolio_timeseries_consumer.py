# tests/unit/services/timeseries-generator-service/consumers/test_portfolio_timeseries_consumer.py
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import date
from decimal import Decimal

from portfolio_common.events import PortfolioAggregationRequiredEvent
from portfolio_common.database_models import (
    Portfolio, PositionTimeseries, Cashflow, Instrument, FxRate, PortfolioTimeseries
)
from services.timeseries_generator_service.app.consumers.portfolio_timeseries_consumer import PortfolioTimeseriesConsumer

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

async def test_process_message_success(consumer: PortfolioTimeseriesConsumer, mock_event: PortfolioAggregationRequiredEvent, mock_kafka_message: MagicMock):
    """
    GIVEN a portfolio aggregation event
    WHEN the message is processed
    THEN it should aggregate data, save the new timeseries record, and update the job status.
    """
    # ARRANGE
    mock_db_session = AsyncMock()
    # FIX: Make .begin() a sync method returning an async context manager
    mock_db_session.begin.return_value = AsyncMock().__aenter__()
    
    async def get_db_session_gen():
        yield mock_db_session

    mock_repo = AsyncMock()
    mock_outbox_repo = AsyncMock()

    # Mock the data fetched by the logic and consumer
    mock_repo.get_portfolio.return_value = Portfolio(portfolio_id=mock_event.portfolio_id, base_currency="USD")
    mock_repo.get_all_position_timeseries_for_date.return_value = [
        PositionTimeseries(security_id="SEC_USD", eod_market_value=Decimal("1000"))
    ]
    mock_repo.get_portfolio_level_cashflows_for_date.return_value = []
    mock_repo.get_instruments_by_ids.return_value = [Instrument(security_id="SEC_USD", currency="USD")]
    mock_repo.get_last_portfolio_timeseries_before.return_value = None # First day

    # Mock the _update_job_status method since it creates its own session
    with patch(
        "services.timeseries_generator_service.app.consumers.portfolio_timeseries_consumer.get_async_db_session", new=get_db_session_gen
    ), patch(
        "services.timeseries_generator_service.app.consumers.portfolio_timeseries_consumer.TimeseriesRepository", return_value=mock_repo
    ), patch(
        "services.timeseries_generator_service.app.consumers.portfolio_timeseries_consumer.OutboxRepository", return_value=mock_outbox_repo
    ), patch.object(
        consumer, '_update_job_status', new_callable=AsyncMock
    ) as mock_update_status:
        
        # ACT
        await consumer.process_message(mock_kafka_message)

        # ASSERT
        # 1. Verify correct data was fetched
        mock_repo.get_portfolio.assert_called_once_with(mock_event.portfolio_id)
        mock_repo.get_all_position_timeseries_for_date.assert_called_once()
        mock_repo.get_portfolio_level_cashflows_for_date.assert_called_once()

        # 2. Verify the new portfolio timeseries record was saved
        mock_repo.upsert_portfolio_timeseries.assert_called_once()
        saved_record = mock_repo.upsert_portfolio_timeseries.call_args[0][0]
        assert isinstance(saved_record, PortfolioTimeseries)
        assert saved_record.eod_market_value == Decimal("1000")

        # 3. Verify an outbox event was created
        mock_outbox_repo.create_outbox_event.assert_called_once()

        # 4. Verify the job status was updated to COMPLETE
        mock_update_status.assert_called_once_with(mock_event.portfolio_id, mock_event.aggregation_date, 'COMPLETE', db_session=mock_db_session)
        
        # 5. Verify no DLQ message was sent
        consumer._send_to_dlq_async.assert_not_called()