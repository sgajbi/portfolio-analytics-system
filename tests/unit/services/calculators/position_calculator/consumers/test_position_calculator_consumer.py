# tests/unit/services/calculators/position_calculator/consumers/test_position_calculator_consumer.py
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, date
from decimal import Decimal

from src.services.calculators.position_calculator.app.consumers.transaction_event_consumer import TransactionEventConsumer
from portfolio_common.events import TransactionEvent
from portfolio_common.database_models import PositionHistory, Transaction as DBTransaction
from portfolio_common.idempotency_repository import IdempotencyRepository
from src.services.calculators.position_calculator.app.repositories.position_repository import PositionRepository

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
    """Provides a consistent transaction event for tests. This represents the new event being processed."""
    return TransactionEvent(
        transaction_id="TXN_POS_CALC_02",
        portfolio_id="PORT_POS_CALC_01",
        security_id="SEC_POS_CALC_01",
        instrument_id="INST_POS_CALC_01",
        transaction_date=datetime(2025, 8, 6, 10, 0, 0),
        transaction_type="SELL",
        quantity=Decimal(40),
        price=Decimal(110),
        gross_transaction_amount=Decimal(4400),
        net_cost=Decimal("-4000"), # COGS for the sale
        net_cost_local=Decimal("-4000"),
        trade_currency="USD",
        currency="USD"
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

async def test_consumer_uses_real_position_logic(position_consumer: TransactionEventConsumer, mock_kafka_message: MagicMock, mock_transaction_event: TransactionEvent):
    """
    GIVEN a new transaction event
    WHEN the consumer processes it using the real PositionCalculator
    THEN it should recalculate positions correctly and stage them for saving.
    """
    # ARRANGE
    mock_idempotency_repo = AsyncMock(spec=IdempotencyRepository)
    mock_idempotency_repo.is_event_processed.return_value = False
    
    mock_outbox_repo = MagicMock()
    mock_position_repo = AsyncMock(spec=PositionRepository)

    # Setup mock repository to return data needed by PositionCalculator.calculate
    # 1. An anchor position before the transaction date
    anchor_position = PositionHistory(
        id=100, portfolio_id="PORT_POS_CALC_01", security_id="SEC_POS_CALC_01",
        position_date=date(2025, 8, 5), quantity=Decimal(100), cost_basis=Decimal(10000), cost_basis_local=Decimal(10000)
    )
    mock_position_repo.get_last_position_before.return_value = anchor_position

    # 2. A list of transactions on or after the transaction date (just the one from the event)
    transaction_from_db = DBTransaction(**mock_transaction_event.model_dump())
    mock_position_repo.get_transactions_on_or_after.return_value = [transaction_from_db]

    # FIX: Simulate the database assigning an ID to new PositionHistory objects
    def simulate_save_positions(positions: list[PositionHistory]):
        for i, pos in enumerate(positions, start=101): # Start IDs at 101
            pos.id = i
    
    mock_position_repo.save_positions.side_effect = simulate_save_positions


    mock_db_session = AsyncMock()
    mock_db_session.begin.return_value = AsyncMock()
    async def mock_get_db_session_generator():
        yield mock_db_session

    with patch(
        "src.services.calculators.position_calculator.app.consumers.transaction_event_consumer.get_async_db_session", new=mock_get_db_session_generator
    ), patch(
        "src.services.calculators.position_calculator.app.consumers.transaction_event_consumer.IdempotencyRepository", return_value=mock_idempotency_repo
    ), patch(
        "src.services.calculators.position_calculator.app.consumers.transaction_event_consumer.PositionRepository", return_value=mock_position_repo
    ), patch(
        "src.services.calculators.position_calculator.app.consumers.transaction_event_consumer.OutboxRepository", return_value=mock_outbox_repo
    ):
        
        # ACT
        await position_consumer.process_message(mock_kafka_message)

        # ASSERT
        mock_idempotency_repo.is_event_processed.assert_called_once()
        mock_position_repo.get_last_position_before.assert_called_once()
        mock_position_repo.get_transactions_on_or_after.assert_called_once()
        mock_position_repo.delete_positions_from.assert_called_once()

        # Assert that the logic produced the correct new position state
        mock_position_repo.save_positions.assert_called_once()
        saved_positions = mock_position_repo.save_positions.call_args[0][0]
        assert len(saved_positions) == 1
        new_pos = saved_positions[0]
        assert new_pos.quantity == Decimal(60) # 100 (anchor) - 40 (sell)
        assert new_pos.cost_basis == Decimal(6000) # 10000 (anchor) - 4000 (COGS)
        assert new_pos.id is not None # Check that the ID was populated by our side_effect

        mock_outbox_repo.create_outbox_event.assert_called_once()
        mock_idempotency_repo.mark_event_processed.assert_called_once()


async def test_process_message_skips_processed_event(position_consumer: TransactionEventConsumer, mock_kafka_message: MagicMock):
    """
    GIVEN an event that has already been processed
    WHEN the consumer processes the message
    THEN it should skip all logic and not publish any events.
    """
    # Arrange
    mock_idempotency_repo = AsyncMock()
    mock_idempotency_repo.is_event_processed.return_value = True # DUPLICATE event
    mock_position_repo = AsyncMock(spec=PositionRepository)

    mock_db_session = AsyncMock()
    mock_db_session.begin.return_value = AsyncMock()
    async def mock_get_db_session_generator():
        yield mock_db_session

    with patch(
        "src.services.calculators.position_calculator.app.consumers.transaction_event_consumer.get_async_db_session", new=mock_get_db_session_generator
    ), patch(
        "src.services.calculators.position_calculator.app.consumers.transaction_event_consumer.IdempotencyRepository", return_value=mock_idempotency_repo
    ), patch(
        "src.services.calculators.position_calculator.app.consumers.transaction_event_consumer.PositionRepository", return_value=mock_position_repo
    ):
        
        # Act
        await position_consumer.process_message(mock_kafka_message)

        # Assert
        mock_idempotency_repo.is_event_processed.assert_called_once()
        # The core logic methods should not have been called
        mock_position_repo.get_last_position_before.assert_not_called()
        mock_position_repo.get_transactions_on_or_after.assert_not_called()