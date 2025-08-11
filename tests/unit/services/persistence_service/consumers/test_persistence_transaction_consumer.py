# tests/unit/services/persistence_service/consumers/test_persistence_transaction_consumer.py
import json
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from contextlib import asynccontextmanager

from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.events import TransactionEvent
from src.services.persistence_service.app.consumers.transaction_consumer import TransactionPersistenceConsumer

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


async def test_process_message_success(
    transaction_consumer: TransactionPersistenceConsumer,
    mock_kafka_message: MagicMock,
    valid_transaction_event: TransactionEvent
):
    """
    GIVEN a valid transaction message
    WHEN the process_message method is called
    THEN it should call the repository to save the transaction
    AND publish a completion event.
    """
    # ARRANGE: Use the robust async context manager mocking pattern
    mock_db_session = AsyncMock()
    mock_db_session.begin.return_value = AsyncMock().__aenter__() # Correct for 'async with'

    # FIX: Use a simple async generator for the 'async for' loop, not a context manager
    async def mock_get_db_session_generator():
        yield mock_db_session

    mock_repo = AsyncMock()
    mock_repo.check_portfolio_exists.return_value = True # Assume portfolio exists
    mock_outbox_repo = AsyncMock()
    mock_idempotency_repo = AsyncMock()
    mock_idempotency_repo.is_event_processed.return_value = False

    with patch(
        "src.services.persistence_service.app.consumers.transaction_consumer.get_async_db_session", new=mock_get_db_session_generator
    ), patch(
        "src.services.persistence_service.app.consumers.transaction_consumer.TransactionDBRepository", return_value=mock_repo
    ), patch(
        "src.services.persistence_service.app.consumers.transaction_consumer.OutboxRepository", return_value=mock_outbox_repo
    ), patch(
        "src.services.persistence_service.app.consumers.transaction_consumer.IdempotencyRepository", return_value=mock_idempotency_repo
    ):
        # ACT
        await transaction_consumer._process_message_with_retry(mock_kafka_message)

        # ASSERT
        mock_repo.create_or_update_transaction.assert_called_once()
        mock_outbox_repo.create_outbox_event.assert_called_once()
        transaction_consumer._send_to_dlq_async.assert_not_called()