# tests/unit/services/calculators/position_calculator/consumers/test_position_calculator_consumer.py
import pytest
from unittest.mock import MagicMock, patch, AsyncMock, ANY
from datetime import datetime, date
from decimal import Decimal
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession
from src.services.calculators.position_calculator.app.consumers.transaction_event_consumer import TransactionEventConsumer, RecalculationInProgressError
from portfolio_common.events import TransactionEvent
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.position_state_repository import PositionStateRepository
from src.services.calculators.position_calculator.app.repositories.position_repository import PositionRepository
from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.database_models import PositionState

pytestmark = pytest.mark.asyncio

@pytest.fixture
def position_consumer():
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
    return TransactionEvent(
        transaction_id="TXN_POS_CALC_02", portfolio_id="PORT_POS_CALC_01",
        instrument_id="INST_POS_CALC_01", security_id="SEC_POS_CALC_01",
        transaction_date=datetime(2025, 8, 6, 10, 0, 0), transaction_type="SELL",
        quantity=Decimal(40), price=Decimal(110), gross_transaction_amount=Decimal(4400),
        net_cost=Decimal("-4000"), net_cost_local=Decimal("-3600"),
        trade_currency="USD", currency="USD"
    )

@pytest.fixture
def mock_kafka_message(mock_transaction_event: TransactionEvent):
    mock_msg = MagicMock()
    mock_msg.value.return_value = mock_transaction_event.model_dump_json().encode('utf-8')
    mock_msg.key.return_value = "test_key".encode('utf-8')
    mock_msg.headers.return_value = []
    mock_msg.topic.return_value = "test"
    mock_msg.partition.return_value = 0
    mock_msg.offset.return_value = 1
    return mock_msg

@pytest.fixture
def mock_dependencies():
    mock_idempotency_repo = AsyncMock(spec=IdempotencyRepository)
    mock_position_state_repo = AsyncMock(spec=PositionStateRepository)
    mock_position_repo = AsyncMock(spec=PositionRepository)

    mock_db_session = AsyncMock(spec=AsyncSession)
    
    @asynccontextmanager
    async def mock_begin_transaction():
        yield
    mock_db_session.begin.side_effect = mock_begin_transaction

    async def get_session_gen():
        yield mock_db_session

    with patch("src.services.calculators.position_calculator.app.consumers.transaction_event_consumer.get_async_db_session", new=get_session_gen), \
         patch("src.services.calculators.position_calculator.app.consumers.transaction_event_consumer.IdempotencyRepository", return_value=mock_idempotency_repo), \
         patch("src.services.calculators.position_calculator.app.consumers.transaction_event_consumer.PositionRepository", return_value=mock_position_repo), \
         patch("src.services.calculators.position_calculator.app.consumers.transaction_event_consumer.PositionStateRepository", return_value=mock_position_state_repo), \
         patch("src.services.calculators.position_calculator.app.consumers.transaction_event_consumer.PositionCalculator.calculate") as mock_calculate:
        yield {
            "idempotency_repo": mock_idempotency_repo,
            "position_state_repo": mock_position_state_repo,
            "position_repo": mock_position_repo,
            "calculate_logic": mock_calculate
        }

async def test_consumer_calls_logic_with_correct_state(position_consumer: TransactionEventConsumer, mock_kafka_message: MagicMock, mock_dependencies: dict):
    # ARRANGE
    mock_dependencies["idempotency_repo"].is_event_processed.return_value = False
    mock_state = PositionState(epoch=0)
    mock_dependencies["position_state_repo"].get_or_create_state.return_value = mock_state

    # ACT
    await position_consumer.process_message(mock_kafka_message)

    # ASSERT
    mock_dependencies["calculate_logic"].assert_awaited_once()
    call_kwargs = mock_dependencies["calculate_logic"].call_args.kwargs
    assert call_kwargs['current_state'] == mock_state

async def test_consumer_discards_stale_epoch_message(position_consumer: TransactionEventConsumer, mock_kafka_message: MagicMock, mock_dependencies: dict):
    """
    GIVEN a Kafka message with a 'reprocess_epoch' header that is less than the current state epoch
    WHEN the consumer processes it
    THEN it should discard the message and not call the business logic.
    """
    # ARRANGE
    mock_dependencies["idempotency_repo"].is_event_processed.return_value = False
    # The database state has a newer epoch
    mock_state = PositionState(epoch=2)
    mock_dependencies["position_state_repo"].get_or_create_state.return_value = mock_state
    # The incoming message has a stale epoch header
    mock_kafka_message.headers.return_value = [('reprocess_epoch', b'1')]

    # ACT
    await position_consumer.process_message(mock_kafka_message)

    # ASSERT
    mock_dependencies["position_state_repo"].get_or_create_state.assert_awaited_once()
    # Ensure the core logic was NOT called
    mock_dependencies["calculate_logic"].assert_not_called()
    # Ensure the event was still marked as processed for idempotency
    mock_dependencies["idempotency_repo"].mark_event_processed.assert_called_once()