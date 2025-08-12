# tests/unit/services/calculators/position_calculator/consumers/test_position_calculator_consumer.py
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, date
from decimal import Decimal
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession
from src.services.calculators.position_calculator.app.consumers.transaction_event_consumer import TransactionEventConsumer
from portfolio_common.events import TransactionEvent
from portfolio_common.database_models import PositionHistory
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.valuation_job_repository import ValuationJobRepository
from portfolio_common.logging_utils import correlation_id_var
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
    """Provides a consistent SELL transaction event for tests."""
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
        net_cost=Decimal("-4000"),
        net_cost_local=Decimal("-3600"),
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
    mock_msg.headers.return_value = [('correlation_id', b'test-corr-id')]
    return mock_msg

async def test_consumer_recalculates_positions_and_creates_job(
    position_consumer: TransactionEventConsumer,
    mock_kafka_message: MagicMock,
    mock_transaction_event: TransactionEvent
):
    """
    GIVEN a new transaction event and an existing position in the database
    WHEN the consumer processes the message
    THEN it should use the real logic to calculate the new position, save it,
    and create a corresponding valuation job.
    """
    # ARRANGE
    mock_idempotency_repo = AsyncMock(spec=IdempotencyRepository)
    mock_idempotency_repo.is_event_processed.return_value = False
    
    mock_valuation_job_repo = AsyncMock(spec=ValuationJobRepository)
    mock_position_repo = AsyncMock(spec=PositionRepository)

    anchor_position = PositionHistory(
        id=100, portfolio_id="PORT_POS_CALC_01", security_id="SEC_POS_CALC_01",
        position_date=date(2025, 8, 5),
        quantity=Decimal(100),
        cost_basis=Decimal(10000),
        cost_basis_local=Decimal(9000)
    )
    mock_position_repo.get_last_position_before.return_value = anchor_position

    mock_db_session = AsyncMock(spec=AsyncSession)
    # --- FIX: `begin` must be an awaitable mock ---
    mock_db_session.begin = AsyncMock()
    mock_transaction = AsyncMock()
    mock_db_session.begin.return_value = mock_transaction
    
    async def get_session_gen():
        yield mock_db_session
    
    with patch(
        "src.services.calculators.position_calculator.app.consumers.transaction_event_consumer.get_async_db_session", new=get_session_gen
    ), patch(
        "src.services.calculators.position_calculator.app.consumers.transaction_event_consumer.IdempotencyRepository", return_value=mock_idempotency_repo
    ), patch(
        "src.services.calculators.position_calculator.app.consumers.transaction_event_consumer.PositionRepository", return_value=mock_position_repo
    ), patch(
        "src.services.calculators.position_calculator.app.consumers.transaction_event_consumer.ValuationJobRepository", return_value=mock_valuation_job_repo
    ):
        
        token = correlation_id_var.set('test-corr-id')
        try:
            # ACT
            await position_consumer.process_message(mock_kafka_message)
        finally:
            correlation_id_var.reset(token)

        # ASSERT
        mock_idempotency_repo.is_event_processed.assert_called_once()
        mock_position_repo.get_last_position_before.assert_called_once()
        mock_position_repo.delete_positions_from.assert_called_once()
        mock_position_repo.save_positions.assert_called_once()
        
        saved_positions = mock_position_repo.save_positions.call_args[0][0]
        assert len(saved_positions) == 1
        new_pos = saved_positions[0]
        
        assert new_pos.quantity == Decimal(60)
        assert new_pos.cost_basis == Decimal(6000)
        assert new_pos.cost_basis_local == Decimal(5400)
        assert new_pos.position_date == mock_transaction_event.transaction_date.date()

        mock_valuation_job_repo.upsert_job.assert_called_once_with(
            portfolio_id=new_pos.portfolio_id,
            security_id=new_pos.security_id,
            valuation_date=new_pos.position_date,
            correlation_id='test-corr-id'
        )
        mock_idempotency_repo.mark_event_processed.assert_called_once()