# tests/unit/services/calculators/position_calculator/consumers/test_position_calculator_consumer.py
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, date
from decimal import Decimal
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession
from src.services.calculators.position_calculator.app.consumers.transaction_event_consumer import TransactionEventConsumer, RecalculationInProgressError
from portfolio_common.events import TransactionEvent
from portfolio_common.database_models import PositionHistory, Transaction as DBTransaction
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.recalculation_job_repository import RecalculationJobRepository
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

@pytest.fixture
def mock_dependencies():
    """A fixture to patch all external dependencies for a consumer test."""
    mock_idempotency_repo = AsyncMock(spec=IdempotencyRepository)
    mock_recalc_job_repo = AsyncMock(spec=RecalculationJobRepository)
    
    mock_position_repo = AsyncMock(spec=PositionRepository)
    mock_position_repo.get_latest_business_date = AsyncMock()

    mock_db_session = AsyncMock(spec=AsyncSession)
    
    @asynccontextmanager
    async def mock_begin_transaction():
        yield
    mock_db_session.begin.side_effect = mock_begin_transaction
    
    async def get_session_gen():
        yield mock_db_session

    with patch(
        "src.services.calculators.position_calculator.app.consumers.transaction_event_consumer.get_async_db_session", new=get_session_gen
    ), patch(
        "src.services.calculators.position_calculator.app.consumers.transaction_event_consumer.IdempotencyRepository", return_value=mock_idempotency_repo
    ), patch(
        "src.services.calculators.position_calculator.app.consumers.transaction_event_consumer.PositionRepository", return_value=mock_position_repo
    ), patch(
        "src.services.calculators.position_calculator.app.consumers.transaction_event_consumer.RecalculationJobRepository", return_value=mock_recalc_job_repo
    ), patch(
        "src.services.calculators.position_calculator.app.consumers.transaction_event_consumer.PositionCalculator.calculate"
    ) as mock_calculate:
        yield {
            "idempotency_repo": mock_idempotency_repo,
            "recalc_job_repo": mock_recalc_job_repo,
            "position_repo": mock_position_repo,
            "calculate_logic": mock_calculate
        }

async def test_consumer_recalculates_positions(
    position_consumer: TransactionEventConsumer,
    mock_kafka_message: MagicMock,
    mock_dependencies: dict
):
    """
    GIVEN a new transaction event
    WHEN the consumer processes the message
    THEN it should call the position calculation logic.
    """
    # ARRANGE
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]
    mock_idempotency_repo.is_event_processed.return_value = False
    
    mock_recalc_job_repo = mock_dependencies["recalc_job_repo"]
    mock_recalc_job_repo.is_job_processing.return_value = False

    mock_position_repo = mock_dependencies["position_repo"]
    mock_position_repo.get_latest_business_date.return_value = date(2025, 8, 7) 

    # ACT
    await position_consumer.process_message(mock_kafka_message)

    # ASSERT
    mock_dependencies["calculate_logic"].assert_awaited_once()
    mock_idempotency_repo.mark_event_processed.assert_called_once()
    mock_recalc_job_repo.upsert_job.assert_not_called()


async def test_consumer_triggers_recalc_for_backdated_txn(
    position_consumer: TransactionEventConsumer,
    mock_kafka_message: MagicMock,
    mock_transaction_event: TransactionEvent,
    mock_dependencies: dict
):
    """
    GIVEN a backdated transaction event
    WHEN the consumer processes it
    THEN it should create a recalculation job.
    """
    # ARRANGE
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]
    mock_idempotency_repo.is_event_processed.return_value = False
    
    mock_recalc_job_repo = mock_dependencies["recalc_job_repo"]
    mock_recalc_job_repo.is_job_processing.return_value = False

    mock_position_repo = mock_dependencies["position_repo"]

    mock_position_repo.get_latest_business_date.return_value = date(2025, 8, 10)

    # ACT
    await position_consumer.process_message(mock_kafka_message)
    
    # ASSERT
    mock_recalc_job_repo.upsert_job.assert_called_once_with(
        portfolio_id=mock_transaction_event.portfolio_id,
        security_id=mock_transaction_event.security_id,
        from_date=mock_transaction_event.transaction_date.date(),
        correlation_id='test-corr-id'
    )
    mock_idempotency_repo.mark_event_processed.assert_called_once()


async def test_consumer_requeues_if_job_is_processing(
    position_consumer: TransactionEventConsumer,
    mock_kafka_message: MagicMock,
    mock_dependencies: dict
):
    """
    GIVEN a transaction for a position that is currently being recalculated
    WHEN the consumer processes it
    THEN it should raise a retryable error to requeue the message.
    """
    # ARRANGE
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]
    mock_idempotency_repo.is_event_processed.return_value = False
    
    mock_recalc_job_repo = mock_dependencies["recalc_job_repo"]

    mock_recalc_job_repo.is_job_processing.return_value = True

    # ACT & ASSERT
    with pytest.raises(RecalculationInProgressError):
        await position_consumer.process_message(mock_kafka_message)

    # Verify that no business logic was run
    mock_dependencies["calculate_logic"].assert_not_called()
    mock_idempotency_repo.mark_event_processed.assert_not_called()