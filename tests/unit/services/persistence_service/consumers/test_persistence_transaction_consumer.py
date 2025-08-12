# tests/unit/services/persistence_service/consumers/test_persistence_transaction_consumer.py
import json
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession
from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.events import TransactionEvent
from src.services.persistence_service.app.consumers.transaction_consumer import TransactionPersistenceConsumer
from src.services.persistence_service.app.repositories.transaction_db_repo import TransactionDBRepository
from portfolio_common.outbox_repository import OutboxRepository
from portfolio_common.idempotency_repository import IdempotencyRepository


# Mark all tests in this file as asyncio
pytestmark = pytest.mark.asyncio

@pytest.fixture
def transaction_consumer():
    """Provides an instance of the consumer for testing."""
    consumer = TransactionPersistenceConsumer(
        bootstrap_servers="mock_server",
        topic="raw_transactions",
        group_id="test_group",
        dlq_topic="persistence.dlq"
    )
    consumer._send_to_dlq_async = AsyncMock()
    return consumer

@pytest.fixture
def valid_transaction_event():
    """Provides a valid TransactionEvent object."""
    return TransactionEvent(
        transaction_id="UNIT_TEST_01",
        portfolio_id="PORT_UT_01",
        instrument_id="INST_UT_01",
        security_id="SEC_UT_01",
        transaction_date="2025-07-31T12:00:00",
        transaction_type="BUY",
        quantity=100,
        price=50,
        gross_transaction_amount=5000,
        trade_currency="USD",
        currency="USD",
    )

@pytest.fixture
def mock_kafka_message(valid_transaction_event: TransactionEvent):
    """Creates a mock Kafka message containing a valid transaction."""
    mock_message = MagicMock()
    mock_message.value.return_value = valid_transaction_event.model_dump_json().encode('utf-8')
    mock_message.key.return_value = "test_key".encode('utf-8')
    mock_message.error.return_value = None
    mock_message.topic.return_value = "raw_transactions"
    mock_message.partition.return_value = 0
    mock_message.offset.return_value = 1
    mock_message.headers.return_value = [('correlation_id', b'test-corr-id')]
    return mock_message

@pytest.fixture
def mock_dependencies():
    """A fixture to patch all external dependencies for a consumer test."""
    mock_repo = AsyncMock(spec=TransactionDBRepository)
    mock_outbox_repo = AsyncMock(spec=OutboxRepository)
    mock_idempotency_repo = AsyncMock(spec=IdempotencyRepository)

    mock_db_session = AsyncMock(spec=AsyncSession)
    mock_transaction = AsyncMock()
    # FIX: `begin` must be an awaitable mock that returns the transaction object
    mock_db_session.begin = AsyncMock(return_value=mock_transaction)
    
    async def get_session_gen():
        yield mock_db_session

    with patch(
        "src.services.persistence_service.app.consumers.transaction_consumer.get_async_db_session", new=get_session_gen
    ), patch(
        "src.services.persistence_service.app.consumers.transaction_consumer.TransactionDBRepository", return_value=mock_repo
    ), patch(
        "src.services.persistence_service.app.consumers.transaction_consumer.OutboxRepository", return_value=mock_outbox_repo
    ), patch(
        "src.services.persistence_service.app.consumers.transaction_consumer.IdempotencyRepository", return_value=mock_idempotency_repo
    ):
        yield {
            "repo": mock_repo,
            "outbox_repo": mock_outbox_repo,
            "idempotency_repo": mock_idempotency_repo,
        }

async def test_process_message_success(
    transaction_consumer: TransactionPersistenceConsumer,
    mock_kafka_message: MagicMock,
    mock_dependencies: dict
):
    """
    GIVEN a valid transaction message
    WHEN the process_message method is called
    THEN it should call the repository to save the transaction
    AND publish a completion event.
    """
    # ARRANGE
    mock_repo = mock_dependencies["repo"]
    mock_outbox_repo = mock_dependencies["outbox_repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]
    
    mock_repo.check_portfolio_exists.return_value = True
    mock_idempotency_repo.is_event_processed.return_value = False

    # ACT
    await transaction_consumer._process_message_with_retry(mock_kafka_message)

    # ASSERT
    mock_repo.create_or_update_transaction.assert_called_once()
    mock_outbox_repo.create_outbox_event.assert_called_once()
    transaction_consumer._send_to_dlq_async.assert_not_called()