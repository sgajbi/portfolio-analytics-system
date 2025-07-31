# services/calculators/cashflow_calculator_service/tests/unit/consumers/test_transaction_consumer.py
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime
from decimal import Decimal

from portfolio_common.kafka_consumer import correlation_id_cv
from portfolio_common.events import TransactionEvent, CashflowCalculatedEvent
from portfolio_common.database_models import Cashflow
from portfolio_common.config import KAFKA_CASHFLOW_CALCULATED_TOPIC
from services.calculators.cashflow_calculator_service.app.consumers.transaction_consumer import CashflowCalculatorConsumer

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
    consumer._producer = MagicMock()
    consumer._send_to_dlq = AsyncMock()
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
        transaction_type="BUY",
        quantity=Decimal("100"),
        price=Decimal("10"),
        gross_transaction_amount=Decimal("1000"),
        trade_fee=Decimal("5.50"),
        trade_currency="USD",
        currency="USD",
    )
    mock_message = MagicMock()
    mock_message.value.return_value = event.model_dump_json().encode('utf-8')
    mock_message.key.return_value = event.portfolio_id.encode('utf-8')
    mock_message.error.return_value = None
    return mock_message

async def test_process_message_success(
    cashflow_consumer: CashflowCalculatorConsumer,
    mock_kafka_message: MagicMock
):
    """
    GIVEN a valid transaction message for a BUY
    WHEN the process_message method is called
    THEN it should call the repository to save the calculated cashflow
    AND publish a cashflow_calculated event.
    """
    # Arrange
    mock_repo = MagicMock()
    # Simulate the repository returning a saved object with an ID
    mock_saved_cashflow = Cashflow(id=1, transaction_id="TXN_CASHFLOW_CONSUMER")
    mock_repo.create_cashflow.return_value = mock_saved_cashflow

    correlation_id = 'corr-cf-789'
    correlation_id_cv.set(correlation_id)

    with patch(
        "services.calculators.cashflow_calculator_service.app.consumers.transaction_consumer.get_db_session"
    ), patch(
        "services.calculators.cashflow_calculator_service.app.consumers.transaction_consumer.CashflowRepository", return_value=mock_repo
    ):
        # Act
        await cashflow_consumer.process_message(mock_kafka_message)

        # Assert
        # 1. Verify the repository was called to save the cashflow
        mock_repo.create_cashflow.assert_called_once()
        
        # 2. Verify the producer was called to publish the completion event
        mock_producer = cashflow_consumer._producer
        mock_producer.publish_message.assert_called_once()
        
        # 3. Verify the content of the published message
        publish_args = mock_producer.publish_message.call_args.kwargs
        assert publish_args['topic'] == KAFKA_CASHFLOW_CALCULATED_TOPIC
        assert publish_args['key'] == "TXN_CASHFLOW_CONSUMER"
        
        # The published event is a CashflowCalculatedEvent, check one of its fields
        assert publish_args['value']['cashflow_id'] == mock_saved_cashflow.id

        # 4. Ensure the DLQ method was NOT called
        cashflow_consumer._send_to_dlq.assert_not_called()