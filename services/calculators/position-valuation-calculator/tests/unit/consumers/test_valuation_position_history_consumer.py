# services/calculators/position-valuation-calculator/tests/unit/consumers/test_position_history_consumer.py
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session
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
    c._producer = MagicMock()
    c._send_to_dlq = AsyncMock()
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
    return mock_msg

async def test_process_message_success(consumer: PositionHistoryConsumer, mock_kafka_message: MagicMock, mock_event: PositionHistoryPersistedEvent):
    """
    GIVEN a new position history event
    WHEN the consumer processes the message
    THEN it should create a valued snapshot, mark as processed, and publish a completion event.
    """
    # Arrange
    mock_db_session = MagicMock(spec=Session)
    mock_transaction_context = MagicMock()
    mock_transaction_context.__enter__.return_value = None
    mock_transaction_context.__exit__.return_value = (None, None, None)
    mock_db_session.begin.return_value = mock_transaction_context

    mock_idempotency_repo = MagicMock()
    mock_idempotency_repo.is_event_processed.return_value = False

    mock_position_history = PositionHistory(id=123, quantity=Decimal(100), cost_basis=Decimal(10000), security_id="SEC_VAL_01", portfolio_id="PORT_VAL_01", position_date=date(2025, 8, 1))
    
    # This is the object our mock repository will now return
    mock_returned_snapshot = DailyPositionSnapshot(id=1, portfolio_id="PORT_VAL_01", security_id="SEC_VAL_01", date=date(2025, 8, 1))

    mock_valuation_repo = MagicMock()
    mock_valuation_repo.get_latest_price_for_position.return_value = MarketPrice(price=Decimal("150"))
    # SIMPLIFIED: Mock the return value of the method that is now called
    mock_valuation_repo.upsert_daily_snapshot.return_value = mock_returned_snapshot

    # Mock only the first query to get the position
    mock_db_session.query.return_value.get.return_value = mock_position_history


    with patch('app.consumers.position_history_consumer.get_db_session', return_value=iter([mock_db_session])), \
         patch('app.consumers.position_history_consumer.IdempotencyRepository', return_value=mock_idempotency_repo), \
         patch('app.consumers.position_history_consumer.ValuationRepository', return_value=mock_valuation_repo):

        # Act
        await consumer.process_message(mock_kafka_message)

        # Assert
        mock_idempotency_repo.is_event_processed.assert_called_once()
        mock_valuation_repo.upsert_daily_snapshot.assert_called_once()
        mock_idempotency_repo.mark_event_processed.assert_called_once()
        consumer._producer.publish_message.assert_called_once()
        consumer._send_to_dlq.assert_not_called()

async def test_process_message_skips_processed_event(consumer: PositionHistoryConsumer, mock_kafka_message: MagicMock):
    """
    GIVEN a position history event that has already been processed
    WHEN the consumer processes the message
    THEN it should skip all business logic.
    """
    # Arrange
    mock_db_session = MagicMock(spec=Session)
    mock_transaction_context = MagicMock()
    mock_transaction_context.__enter__.return_value = None
    mock_transaction_context.__exit__.return_value = (None, None, None)
    mock_db_session.begin.return_value = mock_transaction_context

    mock_idempotency_repo = MagicMock()
    mock_idempotency_repo.is_event_processed.return_value = True # DUPLICATE

    mock_valuation_repo = MagicMock()

    with patch('app.consumers.position_history_consumer.get_db_session', return_value=iter([mock_db_session])), \
         patch('app.consumers.position_history_consumer.IdempotencyRepository', return_value=mock_idempotency_repo), \
         patch('app.consumers.position_history_consumer.ValuationRepository', return_value=mock_valuation_repo):

        # Act
        await consumer.process_message(mock_kafka_message)

        # Assert
        mock_idempotency_repo.is_event_processed.assert_called_once()
        mock_valuation_repo.upsert_daily_snapshot.assert_not_called()
        mock_idempotency_repo.mark_event_processed.assert_not_called()
        consumer._producer.publish_message.assert_not_called()
        consumer._send_to_dlq.assert_not_called()