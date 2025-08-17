# tests/unit/services/timeseries-generator-service/consumers/test_position_timeseries_consumer.py
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import date
from decimal import Decimal
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from sqlalchemy.dialects import postgresql
from portfolio_common.events import DailyPositionSnapshotPersistedEvent
from portfolio_common.database_models import DailyPositionSnapshot, PositionTimeseries, Instrument
from services.timeseries_generator_service.app.consumers.position_timeseries_consumer import (
    PositionTimeseriesConsumer, InstrumentNotFoundError
)
from portfolio_common.repositories.timeseries_repository import TimeseriesRepository

pytestmark = pytest.mark.asyncio

@pytest.fixture
def consumer() -> PositionTimeseriesConsumer:
    """Provides a clean instance of the PositionTimeseriesConsumer."""
    consumer = PositionTimeseriesConsumer(
        bootstrap_servers="mock_server",
        topic="daily_position_snapshot_persisted",
        group_id="test_group",
    )
    consumer._send_to_dlq_async = AsyncMock()
    return consumer

@pytest.fixture
def mock_event() -> DailyPositionSnapshotPersistedEvent:
    """Provides a consistent event for tests."""
    return DailyPositionSnapshotPersistedEvent(
        id=123,
        portfolio_id="PORT_TS_POS_01",
        security_id="SEC_TS_POS_01",
        date=date(2025, 8, 12)
    )

@pytest.fixture
def mock_kafka_message(mock_event: DailyPositionSnapshotPersistedEvent) -> MagicMock:
    """Creates a mock Kafka message from the event."""
    mock_msg = MagicMock()
    mock_msg.value.return_value = mock_event.model_dump_json().encode('utf-8')
    mock_msg.headers.return_value = []
    return mock_msg

@pytest.fixture
def mock_dependencies():
    """A fixture to patch all external dependencies for the consumer test."""
    mock_repo = AsyncMock(spec=TimeseriesRepository)
    mock_db_session = AsyncMock(spec=AsyncSession)
    mock_transaction = AsyncMock()
    mock_db_session.begin.return_value = mock_transaction
    
    async def get_session_gen():
        yield mock_db_session

    with patch(
        "services.timeseries_generator_service.app.consumers.position_timeseries_consumer.get_async_db_session", new=get_session_gen
    ), patch(
        "services.timeseries_generator_service.app.consumers.position_timeseries_consumer.TimeseriesRepository", return_value=mock_repo
    ):
        yield {"repo": mock_repo, "db_session": mock_db_session}

async def test_process_message_success(
    consumer: PositionTimeseriesConsumer,
    mock_kafka_message: MagicMock,
    mock_event: DailyPositionSnapshotPersistedEvent,
    mock_dependencies: dict
):
    """
    GIVEN a valid snapshot persisted event
    WHEN the message is processed
    THEN it should calculate the position time series and create an aggregation job.
    """
    # ARRANGE
    mock_repo = mock_dependencies["repo"]
    mock_db_session = mock_dependencies["db_session"]

    mock_repo.get_instrument.return_value = Instrument(security_id=mock_event.security_id, currency="USD")
    mock_db_session.get.return_value = DailyPositionSnapshot(
        id=mock_event.id, quantity=Decimal(100), cost_basis=Decimal(1000), market_value_local=Decimal(1100)
    )
    mock_repo.get_last_position_timeseries_before.return_value = PositionTimeseries(
        eod_market_value=Decimal(1050)
    )
    mock_repo.get_all_cashflows_for_security_date.return_value = []
    mock_repo.is_first_position.return_value = False

    # ACT
    await consumer._process_message_with_retry(mock_kafka_message)

    # ASSERT
    mock_repo.get_instrument.assert_awaited_once_with(mock_event.security_id)
    mock_db_session.get.assert_awaited_once_with(DailyPositionSnapshot, mock_event.id)
    mock_repo.upsert_position_timeseries.assert_awaited_once()
    mock_db_session.execute.assert_awaited_once()

async def test_process_message_raises_retryable_error_if_instrument_missing(
    consumer: PositionTimeseriesConsumer,
    mock_kafka_message: MagicMock,
    mock_dependencies: dict
):
    """
    GIVEN a snapshot event where the instrument data is not yet persisted
    WHEN the message is processed
    THEN it should raise a retryable InstrumentNotFoundError.
    """
    # ARRANGE
    mock_repo = mock_dependencies["repo"]
    mock_repo.get_instrument.return_value = None  # Simulate instrument not found

    # ACT & ASSERT
    with pytest.raises(InstrumentNotFoundError):
        await consumer._process_message_with_retry(mock_kafka_message)

    # Verify that no records were created
    mock_dependencies["db_session"].get.assert_not_called()
    mock_repo.upsert_position_timeseries.assert_not_called()