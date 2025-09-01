# tests/unit/services/calculators/cashflow_calculator_service/unit/consumers/test_cashflow_transaction_consumer.py
import pytest
from unittest.mock import MagicMock, patch, AsyncMock, ANY
from datetime import datetime, date
from decimal import Decimal
from contextlib import asynccontextmanager
import json

from sqlalchemy.ext.asyncio import AsyncSession
from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.events import TransactionEvent, CashflowCalculatedEvent
from portfolio_common.database_models import Cashflow
from src.services.calculators.cashflow_calculator_service.app.consumers.transaction_consumer import CashflowCalculatorConsumer
from src.services.calculators.cashflow_calculator_service.app.repositories.cashflow_repository import CashflowRepository
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.outbox_repository import OutboxRepository

# Mark all tests in this file as asyncio
pytestmark = pytest.mark.asyncio

@pytest.fixture
def cashflow_consumer():
    """Provides an instance of the consumer for testing."""
    consumer = CashflowCalculatorConsumer(
        bootstrap_servers="mock_server",
        topic="raw_transactions_completed",
        group_id="test_group",
        dlq_topic="test.dlq"
    )
    consumer._send_to_dlq_async = AsyncMock()
    return consumer

@pytest.fixture
def mock_kafka_message():
    """Creates a mock Kafka message containing a valid BUY transaction."""
    event = TransactionEvent(
        transaction_id="TXN_CASHFLOW_CONSUMER",
        portfolio_id="PORT_CFC_01",
        instrument_id="INST_CFC_01",
        security_id="SEC_CFC_01",
        transaction_date=datetime(2025, 8, 1, 10, 0, 0),
        transaction_type="BUY", # Default type
        quantity=Decimal("100"),
        price=Decimal("10"),
        gross_transaction_amount=Decimal("1000"),
        trade_fee=Decimal("5.50"),
        trade_currency="USD",
        currency="USD",
        epoch=1
    )
    
    mock_msg = MagicMock()
    mock_msg.value.return_value = event.model_dump_json().encode('utf-8')
    mock_msg.key.return_value = event.portfolio_id.encode('utf-8')
    mock_msg.topic.return_value = "raw_transactions_completed"
    mock_msg.partition.return_value = 0
    mock_msg.offset.return_value = 123
    mock_msg.error.return_value = None
    mock_msg.headers.return_value = [('correlation_id', b'test-corr-id')]
    return mock_msg

@pytest.fixture
def mock_dependencies():
    """A fixture to patch all external dependencies for a consumer test."""
    mock_cashflow_repo = AsyncMock(spec=CashflowRepository)
    mock_idempotency_repo = AsyncMock(spec=IdempotencyRepository)
    mock_outbox_repo = AsyncMock(spec=OutboxRepository)
    
    mock_db_session = AsyncMock(spec=AsyncSession)
    mock_transaction = AsyncMock()
    mock_db_session.begin = AsyncMock(return_value=mock_transaction)
    
    async def get_session_gen():
        yield mock_db_session

    with patch(
        "src.services.calculators.cashflow_calculator_service.app.consumers.transaction_consumer.get_async_db_session", new=get_session_gen
    ), patch(
        "src.services.calculators.cashflow_calculator_service.app.consumers.transaction_consumer.CashflowRepository", return_value=mock_cashflow_repo
    ), patch(
        "src.services.calculators.cashflow_calculator_service.app.consumers.transaction_consumer.IdempotencyRepository", return_value=mock_idempotency_repo
    ), patch(
        "src.services.calculators.cashflow_calculator_service.app.consumers.transaction_consumer.OutboxRepository", return_value=mock_outbox_repo
    ):
        yield {
            "cashflow_repo": mock_cashflow_repo,
            "idempotency_repo": mock_idempotency_repo,
            "outbox_repo": mock_outbox_repo
        }

async def test_process_message_success(
    cashflow_consumer: CashflowCalculatorConsumer,
    mock_kafka_message: MagicMock,
    mock_dependencies: dict
):
    """
    GIVEN a valid new transaction message
    WHEN the process_message method is called
    THEN it should check for idempotency, call the repository, mark as processed, and publish an event.
    """
    # Arrange
    mock_cashflow_repo = mock_dependencies["cashflow_repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]
    mock_outbox_repo = mock_dependencies["outbox_repo"]

    mock_idempotency_repo.is_event_processed.return_value = False
    
    mock_saved_cashflow = Cashflow(
        id=1, transaction_id="TXN_CASHFLOW_CONSUMER", portfolio_id="PORT_CFC_01",
        security_id="SEC_CFC_01", cashflow_date=date(2025, 8, 1),
        amount=Decimal("1005.50"), currency="USD", classification="INVESTMENT_OUTFLOW",
        timing="BOD", calculation_type="NET",
        is_position_flow=True,
        is_portfolio_flow=False,
        epoch=1
    )
    mock_cashflow_repo.create_cashflow.return_value = mock_saved_cashflow

    with patch("src.services.calculators.cashflow_calculator_service.app.consumers.transaction_consumer.EpochFencer") as mock_fencer_class:
        mock_fencer_instance = AsyncMock()
        mock_fencer_instance.check.return_value = True
        mock_fencer_class.return_value = mock_fencer_instance
        
        # Act
        await cashflow_consumer.process_message(mock_kafka_message)

        # Assert
        mock_idempotency_repo.is_event_processed.assert_called_once_with("raw_transactions_completed-0-123", "cashflow-calculator")
        mock_cashflow_repo.create_cashflow.assert_called_once()
        mock_outbox_repo.create_outbox_event.assert_called_once()
        
        outbox_payload = mock_outbox_repo.create_outbox_event.call_args.kwargs['payload']
        assert outbox_payload['epoch'] == 1
        
        mock_idempotency_repo.mark_event_processed.assert_called_once()
        cashflow_consumer._send_to_dlq_async.assert_not_called()

async def test_process_message_skips_stale_epoch_event(
    cashflow_consumer: CashflowCalculatorConsumer,
    mock_kafka_message: MagicMock,
    mock_dependencies: dict
):
    """
    GIVEN a transaction message that the EpochFencer flags as stale
    WHEN the process_message method is called
    THEN it should skip all business logic and publishing.
    """
    # Arrange
    mock_cashflow_repo = mock_dependencies["cashflow_repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]
    mock_outbox_repo = mock_dependencies["outbox_repo"]

    # Mock the fencer to return False, indicating a stale event
    with patch("src.services.calculators.cashflow_calculator_service.app.consumers.transaction_consumer.EpochFencer") as mock_fencer_class:
        mock_fencer_instance = AsyncMock()
        mock_fencer_instance.check.return_value = False
        mock_fencer_class.return_value = mock_fencer_instance

        # Act
        await cashflow_consumer.process_message(mock_kafka_message)

        # Assert
        mock_fencer_instance.check.assert_awaited_once()
        mock_idempotency_repo.is_event_processed.assert_not_called()
        mock_cashflow_repo.create_cashflow.assert_not_called()
        mock_outbox_repo.create_outbox_event.assert_not_called()
        cashflow_consumer._send_to_dlq_async.assert_not_called()