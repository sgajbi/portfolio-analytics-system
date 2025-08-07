# services/calculators/position-valuation-calculator/tests/unit/consumers/test_valuation_position_history_consumer.py
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from consumers.position_history_consumer import PositionHistoryConsumer
from portfolio_common.events import PositionHistoryPersistedEvent
from portfolio_common.database_models import PositionHistory, MarketPrice, DailyPositionSnapshot

pytestmark = pytest.mark.asyncio

@pytest.fixture
def consumer():
    """Provides a clean instance of the PositionHistoryConsumer."""
    c = PositionHistoryConsumer(
        bootstrap_servers="mock_server",
        topic="position_history_persisted",
        group_id="test_group",
        dlq_topic="test.dlq"
    )
    c._send_to_dlq_async = AsyncMock()
    return c

@pytest.fixture
def mock_event():
    """Provides a consistent PositionHistoryPersistedEvent for tests."""
    return PositionHistoryPersistedEvent(
        id=123,
        portfolio_id="PORT_VAL_01",
        security_id="SEC_VAL_01",
        position_date=date(2025, 8, 1)
    )

@pytest.fixture
def mock_kafka_message(mock_event: PositionHistoryPersistedEvent):
    """Creates a mock Kafka message from the event."""
    mock_msg = MagicMock()
    mock_msg.value.return_value = mock_event.model_dump_json().encode('utf-8')
    mock_msg.key.return_value = "test_key".encode('utf-8')
    mock_msg.topic.return_value = "position_history_persisted"
    mock_msg.partition.return_value = 0
    mock_msg.offset.return_value = 1
    mock_msg.error.return_value = None
    mock_msg.headers.return_value = []
    return mock_msg

async def test_process_message_success(consumer: PositionHistoryConsumer, mock_kafka_message: MagicMock, mock_event: PositionHistoryPersistedEvent):
    """
    GIVEN a new position history event
    WHEN the consumer processes the message
    THEN it should create a valued snapshot, mark as processed, and publish a completion event.
    """
    # Arrange
    mock_db_session = AsyncMock(spec=AsyncSession)

    mock_idempotency_repo = AsyncMock()
    mock_idempotency_repo.is_event_processed.return_value = False

    mock_position_history = PositionHistory(id=123, quantity=Decimal(100), cost_basis=Decimal(10000), security_id="SEC_VAL_01", portfolio_id="PORT_VAL_01", position_date=date(2025, 8, 1))

    mock_returned_snapshot = DailyPositionSnapshot(id=1, portfolio_id="PORT_VAL_01", security_id="SEC_VAL_01", date=date(2025, 8, 1))

    mock_valuation_repo = AsyncMock()
    mock_valuation_repo.get_latest_price_for_position.return_value = MarketPrice(price=Decimal("150"))
    mock_valuation_repo.upsert_daily_snapshot.return_value = mock_returned_snapshot

    mock_db_session.get.return_value = mock_position_history


    with patch('consumers.position_history_consumer.get_async_db_session', return_value=mock_db_session), \
         patch('consumers.position_history_consumer.IdempotencyRepository', return_value=mock_idempotency_repo), \
         patch('consumers.position_history_consumer.ValuationRepository', return_value=mock_valuation_repo), \
         patch('consumers.position_history_consumer.OutboxRepository') as mock_outbox_repo:

        # Act
        await consumer.process_message(mock_kafka_message)

        # Assert
        mock_idempotency_repo.is_event_processed.assert_called_once()
        mock_valuation_repo.upsert_daily_snapshot.assert_called_once()
        mock_idempotency_repo.mark_event_processed.assert_called_once()
        mock_outbox_repo.return_value.create_outbox_event.assert_called_once()
        consumer._send_to_dlq_async.assert_not_called()