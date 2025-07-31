# services/persistence_service/tests/unit/consumers/test_transaction_consumer.py
import json
import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from portfolio_common.kafka_consumer import correlation_id_cv
from portfolio_common.events import TransactionEvent
from services.persistence_service.app.consumers.transaction_consumer import TransactionPersistenceConsumer

# Mark all tests in this file as asyncio
pytestmark = pytest.mark.asyncio

@pytest.fixture
def transaction_consumer():
    """Provides an instance of the consumer for testing."""
    consumer = TransactionPersistenceConsumer(
        bootstrap_servers="mock_server",
        topic="raw_transactions",
        group_id="test_group",
        dlq_topic="persistence.dlq" # Enable DLQ for testing
    )
    # Manually attach mock producer for unit testing
    consumer._producer = MagicMock()
    # Mock the async DLQ method
    consumer._send_to_dlq = AsyncMock()
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
    mock_repo = MagicMock()
    correlation_id = 'corr-id-123'
    correlation_id_cv.set(correlation_id)

    with patch(
        "services.persistence_service.app.consumers.transaction_consumer.get_db_session"
    ), patch(
        "services.persistence_service.app.consumers.transaction_consumer.TransactionDBRepository", return_value=mock_repo
    ):
        await transaction_consumer.process_message(mock_kafka_message)

        mock_repo.create_or_update_transaction.assert_called_once()
        call_args = mock_repo.create_or_update_transaction.call_args[0][0]
        assert call_args.transaction_id == valid_transaction_event.transaction_id

        mock_producer = transaction_consumer._producer
        mock_producer.publish_message.assert_called_once()
        
        publish_args = mock_producer.publish_message.call_args.kwargs
        assert publish_args['key'] == valid_transaction_event.portfolio_id
        assert publish_args['value']['transaction_id'] == valid_transaction_event.transaction_id
        assert ('X-Correlation-ID', correlation_id.encode('utf-8')) in publish_args['headers']

        # Ensure the DLQ method was NOT called
        transaction_consumer._send_to_dlq.assert_not_called()


async def test_process_message_sends_to_dlq_on_validation_error(
    transaction_consumer: TransactionPersistenceConsumer
):
    """
    GIVEN a message with an invalid transaction payload (missing required fields)
    WHEN the process_message method is called
    THEN it should call the _send_to_dlq method
    AND NOT call the repository or the regular producer.
    """
    # Arrange: Create a message with an invalid payload
    invalid_payload = {"portfolio_id": "PORT_BAD_01"} # Missing transaction_id, etc.
    mock_invalid_message = MagicMock()
    mock_invalid_message.value.return_value = json.dumps(invalid_payload).encode('utf-8')
    mock_invalid_message.key.return_value = "bad_key".encode('utf-8')
    mock_invalid_message.error.return_value = None

    mock_repo = MagicMock()

    # Act
    with patch(
        "services.persistence_service.app.consumers.transaction_consumer.get_db_session"
    ), patch(
        "services.persistence_service.app.consumers.transaction_consumer.TransactionDBRepository", return_value=mock_repo
    ):
        await transaction_consumer.process_message(mock_invalid_message)

        # Assert
        # 1. Verify the DLQ method was called
        transaction_consumer._send_to_dlq.assert_awaited_once()

        # 2. Verify that the main processing logic was NOT called
        mock_repo.create_or_update_transaction.assert_not_called()
        transaction_consumer._producer.publish_message.assert_not_called()