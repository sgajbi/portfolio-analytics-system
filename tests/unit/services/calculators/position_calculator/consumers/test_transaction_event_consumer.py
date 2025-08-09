# services/calculators/position_calculator/tests/unit/consumers/test_transaction_event_consumer.py
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, date
from decimal import Decimal

from services.calculators.position_calculator.app.consumers.transaction_event_consumer import TransactionEventConsumer
from services.calculators.position_calculator.app.core.position_logic import PositionCalculator
from portfolio_common.events import TransactionEvent, PositionHistoryPersistedEvent
from portfolio_common.database_models import PositionHistory
from portfolio_common.config import KAFKA_POSITION_HISTORY_PERSISTED_TOPIC

pytestmark = pytest.mark.asyncio

@pytest.fixture
def position_consumer():
    """Provides a clean instance of the consumer for testing."""
    consumer = TransactionEventConsumer(
        bootstrap_servers="mock_server",
        topic="processed_transactions_completed",
        group_id="test_group",
        dlq_topic="test.dlq"
    )
    consumer._send_to_dlq_async = AsyncMock()
    return consumer

@pytest.fixture
def mock_transaction_event() -> TransactionEvent:
    """Provides a consistent transaction event for tests."""
    return TransactionEvent(
        transaction_id="TXN_POS_CALC_01",
        portfolio_id="PORT_POS_CALC_01",
        security_id="SEC_POS_CALC_01",
        transaction_date=datetime(2025, 8, 5, 10, 0, 0),
        transaction_type="BUY",
        quantity=Decimal(100),
        net_cost=Decimal("10000"),
        instrument_id="NA", price=Decimal(100), gross_transaction_amount=Decimal(10000),
        trade_currency="USD", currency="USD"
    )

@pytest.fixture
def mock_kafka_message(mock_transaction_event: TransactionEvent):
    """Creates a mock Kafka message from a transaction event."""
    mock_msg = MagicMock()
    mock_msg.value.return_value = mock_transaction_event.model_dump_json().encode('utf-8')
    mock_msg.key.return_value = "test_key".encode('utf-8')
    mock_msg.topic.return_value = "processed_transactions_completed"
    mock_msg.partition.return_value = 0
    mock_msg.offset.return_value = 200
    mock_msg.error.return_value = None
    mock_msg.headers.return_value = []
    return mock_msg

async def test_process_message_success(position_consumer: TransactionEventConsumer, mock_kafka_message: MagicMock):
    """
    GIVEN a new transaction event
    WHEN the consumer processes the message
    THEN it should perform the calculation, save results, mark the event as processed, and publish completion events.
    """
    # Arrange
    new_positions = [
        PositionHistory(id=101, transaction_id="TXN_POS_CALC_01", security_id="SEC_POS_CALC_01", portfolio_id="PORT_POS_CALC_01", position_date=date(2025, 8, 5)),
        PositionHistory(id=102, transaction_id="TXN_POS_CALC_02", security_id="SEC_POS_CALC_01", portfolio_id="PORT_POS_CALC_01", position_date=date(2025, 8, 6))
    ]

    mock_idempotency_repo = AsyncMock()
    mock_idempotency_repo.is_event_processed.return_value = False

    # --- FIX: Correct async generator mocking ---
    mock_db_session = AsyncMock()
    mock_db_session.begin.return_value = AsyncMock()
    async def mock_get_db_session_generator():
        yield mock_db_session
    
    with patch(
        "services.calculators.position_calculator.app.consumers.transaction_event_consumer.get_async_db_session", new=mock_get_db_session_generator
    ), patch(
        "services.calculators.position_calculator.app.consumers.transaction_event_consumer.IdempotencyRepository", return_value=mock_idempotency_repo
    ), patch(
        "services.calculators.position_calculator.app.consumers.transaction_event_consumer.PositionRepository"
    ), patch(
        "services.calculators.position_calculator.app.consumers.transaction_event_consumer.OutboxRepository"
    ) as mock_outbox_repo_class, patch(
        "services.calculators.position_calculator.app.consumers.transaction_event_consumer.PositionCalculator.calculate", return_value=new_positions
    ) as mock_calculate:
        
        mock_outbox_instance = mock_outbox_repo_class.return_value

        # Act
        await position_consumer.process_message(mock_kafka_message)

        # Assert
        mock_idempotency_repo.is_event_processed.assert_called_once_with("processed_transactions_completed-0-200", "position-calculator")
        mock_idempotency_repo.mark_event_processed.assert_called_once()
        mock_calculate.assert_called_once()
        
        assert mock_outbox_instance.create_outbox_event.call_count == len(new_positions)

async def test_process_message_skips_processed_event(position_consumer: TransactionEventConsumer, mock_kafka_message: MagicMock):
    """
    GIVEN an event that has already been processed
    WHEN the consumer processes the message
    THEN it should skip all logic and not publish any events.
    """
    # Arrange
    mock_idempotency_repo = AsyncMock()
    mock_idempotency_repo.is_event_processed.return_value = True # DUPLICATE event

    # --- FIX: Correct async generator mocking ---
    mock_db_session = AsyncMock()
    mock_db_session.begin.return_value = AsyncMock()
    async def mock_get_db_session_generator():
        yield mock_db_session

    with patch(
        "services.calculators.position_calculator.app.consumers.transaction_event_consumer.get_async_db_session", new=mock_get_db_session_generator
    ), patch(
        "services.calculators.position_calculator.app.consumers.transaction_event_consumer.IdempotencyRepository", return_value=mock_idempotency_repo
    ), patch(
        "services.calculators.position_calculator.app.consumers.transaction_event_consumer.PositionCalculator.calculate"
    ) as mock_calculate:
        
        # Act
        await position_consumer.process_message(mock_kafka_message)

        # Assert
        mock_idempotency_repo.is_event_processed.assert_called_once()
        mock_calculate.assert_not_called()