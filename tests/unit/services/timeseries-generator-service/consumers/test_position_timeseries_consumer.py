# tests/unit/services/timeseries-generator-service/consumers/test_position_timeseries_consumer.py
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import date
from decimal import Decimal

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import func

from portfolio_common.events import DailyPositionSnapshotPersistedEvent
from portfolio_common.database_models import (
    DailyPositionSnapshot, Instrument, PositionTimeseries, Cashflow, PortfolioAggregationJob
)
from services.timeseries_generator_service.app.consumers.position_timeseries_consumer import (
    PositionTimeseriesConsumer, InstrumentNotFoundError, PreviousTimeseriesNotFoundError
)

pytestmark = pytest.mark.asyncio

@pytest.fixture
def consumer() -> PositionTimeseriesConsumer:
    """Provides a clean instance of the PositionTimeseriesConsumer."""
    consumer = PositionTimeseriesConsumer(
        bootstrap_servers="mock_server",
        topic="daily_position_snapshot_persisted",
        group_id="test_group",
        dlq_topic="test.dlq"
    )
    consumer._send_to_dlq_async = AsyncMock()
    return consumer

@pytest.fixture
def mock_event() -> DailyPositionSnapshotPersistedEvent:
    """Provides a consistent snapshot event for tests."""
    return DailyPositionSnapshotPersistedEvent(
        id=123,
        portfolio_id="PORT_TS_01",
        security_id="SEC_TS_01",
        date=date(2025, 8, 10)
    )

@pytest.fixture
def mock_kafka_message(mock_event: DailyPositionSnapshotPersistedEvent) -> MagicMock:
    """Creates a mock Kafka message from the event."""
    mock_msg = MagicMock()
    mock_msg.value.return_value = mock_event.model_dump_json().encode('utf-8')
    mock_msg.key.return_value = "test_key".encode('utf-8')
    mock_msg.topic.return_value = "daily_position_snapshot_persisted"
    mock_msg.partition.return_value = 0
    mock_msg.offset.return_value = 1
    mock_msg.error.return_value = None
    mock_msg.headers.return_value = []
    return mock_msg

async def test_process_message_success_subsequent_day(consumer: PositionTimeseriesConsumer, mock_event: DailyPositionSnapshotPersistedEvent, mock_kafka_message: MagicMock):
    """
    GIVEN a snapshot event for a security that has a previous day's timeseries
    WHEN the message is processed
    THEN it should calculate the new timeseries record and create an aggregation job.
    """
    # ARRANGE
    mock_db_session = AsyncMock()
    # FIX: Make .begin() a sync method returning an async context manager
    mock_db_session.begin.return_value = AsyncMock().__aenter__()
    
    async def get_db_session_gen():
        yield mock_db_session

    mock_repo = AsyncMock()
    
    # Mock the data fetched from the repository
    mock_repo.get_instrument.return_value = Instrument(security_id=mock_event.security_id, currency="USD")
    mock_db_session.get.return_value = DailyPositionSnapshot(
        id=mock_event.id, portfolio_id=mock_event.portfolio_id, security_id=mock_event.security_id,
        date=mock_event.date, quantity=Decimal(100), cost_basis=Decimal(10000), market_value=Decimal(11000)
    )
    mock_repo.get_last_position_timeseries_before.return_value = PositionTimeseries(
        eod_market_value=Decimal(10500) # Previous day's closing value
    )
    mock_repo.get_all_cashflows_for_security_date.return_value = [
        Cashflow(amount=Decimal("50"), timing="EOD") # e.g. a dividend
    ]
    # Mock the roll-forward to return no other open positions
    mock_repo.get_all_open_positions_as_of.return_value = []

    with patch(
        "services.timeseries_generator_service.app.consumers.position_timeseries_consumer.get_async_db_session", new=get_db_session_gen
    ), patch(
        "services.timeseries_generator_service.app.consumers.position_timeseries_consumer.TimeseriesRepository", return_value=mock_repo
    ):
        # ACT
        await consumer._process_message_with_retry(mock_kafka_message)

    # ASSERT
    # 1. Verify correct data was fetched
    mock_repo.get_instrument.assert_called_once_with(mock_event.security_id)
    mock_repo.get_last_position_timeseries_before.assert_called_once()
    mock_repo.get_all_cashflows_for_security_date.assert_called_once()

    # 2. Verify the new timeseries record was correctly calculated and saved
    mock_repo.upsert_position_timeseries.assert_called_once()
    saved_record = mock_repo.upsert_position_timeseries.call_args[0][0]
    assert isinstance(saved_record, PositionTimeseries)
    assert saved_record.date == mock_event.date
    assert saved_record.bod_market_value == Decimal("10500") # from previous day
    assert saved_record.eod_market_value == Decimal("11000") # from current snapshot
    assert saved_record.eod_cashflow == Decimal("50") # from cashflow records

    # 3. Verify that an aggregation job was created
    # The consumer uses a raw execute, so we check the session mock
    mock_db_session.execute.assert_called_once()
    
    # 4. Verify no DLQ message was sent
    consumer._send_to_dlq_async.assert_not_called()