# services/persistence_service/tests/unit/consumers/test_transaction_consumer.py
import json
import pytest
from unittest.mock import MagicMock, patch

# NEW: Import the context variable we need to set
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
        group_id="test_group"
    )
    consumer._producer = MagicMock()
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
    # Note: We no longer need to mock the headers on the *incoming* message for this test,
    # as we are setting the context directly.
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
    AND publish a completion event with the correct correlation ID.
    """
    # Arrange: Mock the dependencies (database repository)
    mock_repo = MagicMock()

    # Arrange: Set the correlation ID context to simulate the BaseConsumer.run() behavior.
    correlation_id = 'corr-id-123'
    correlation_id_cv.set(correlation_id)

    with patch(
        "services.persistence_service.app.consumers.transaction_consumer.get_db_session"
    ), patch(
        "services.persistence_service.app.consumers.transaction_consumer.TransactionDBRepository", return_value=mock_repo
    ):
        # Act: Process the simulated Kafka message
        await transaction_consumer.process_message(mock_kafka_message)

        # Assert
        # 1. Verify the repository was called correctly
        mock_repo.create_or_update_transaction.assert_called_once()
        call_args = mock_repo.create_or_update_transaction.call_args[0][0]
        assert call_args.transaction_id == valid_transaction_event.transaction_id

        # 2. Verify that the completion event was published
        mock_producer = transaction_consumer._producer
        mock_producer.publish_message.assert_called_once()
        
        # 3. Verify the content of the published message
        publish_args = mock_producer.publish_message.call_args.kwargs
        assert publish_args['key'] == valid_transaction_event.portfolio_id
        assert publish_args['value']['transaction_id'] == valid_transaction_event.transaction_id
        # 4. Verify correlation ID header was correctly created and passed through
        assert ('X-Correlation-ID', correlation_id.encode('utf-8')) in publish_args['headers']