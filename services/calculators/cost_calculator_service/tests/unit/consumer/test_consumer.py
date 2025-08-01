# services/calculators/cost_calculator_service/tests/unit/consumer/test_consumer.py
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
from decimal import Decimal

from portfolio_common.events import TransactionEvent
from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.config import KAFKA_PROCESSED_TRANSACTIONS_COMPLETED_TOPIC
from src.core.models.transaction import Transaction as EngineTransaction
from services.calculators.cost_calculator_service.app.consumer import CostCalculatorConsumer
from services.calculators.cost_calculator_service.app.repository import CostCalculatorRepository
from portfolio_common.idempotency_repository import IdempotencyRepository # NEW IMPORT

@pytest.fixture
def cost_calculator_consumer():
    """Provides an instance of the consumer with a mocked producer."""
    consumer = CostCalculatorConsumer(
        bootstrap_servers="mock_server",
        topic="raw_transactions_completed",
        group_id="test_group"
    )
    consumer._producer = MagicMock()
    return consumer

@pytest.fixture
def mock_kafka_message():
    """Provides a reusable mock Kafka message."""
    sell_event = TransactionEvent(
        transaction_id="SELL01", portfolio_id="PORT_COST_01", instrument_id="AAPL",
        security_id="SEC_COST_01", transaction_date=datetime(2025, 1, 20),
        transaction_type="SELL", quantity=Decimal("10"), price=Decimal("175.0"),
        gross_transaction_amount=Decimal("1750.0"), trade_currency="USD", currency="USD"
    )
    mock_msg = MagicMock()
    mock_msg.value.return_value = sell_event.model_dump_json().encode('utf-8')
    mock_msg.topic.return_value = "raw_transactions_completed"
    mock_msg.partition.return_value = 0
    mock_msg.offset.return_value = 1
    mock_msg.headers.return_value = None
    return mock_msg

def test_process_message_with_existing_history(cost_calculator_consumer: CostCalculatorConsumer, mock_kafka_message: MagicMock):
    """
    GIVEN a new transaction message
    WHEN the process_message method is called
    THEN it should check idempotency, process the event, update the DB, mark as processed, and publish.
    """
    # ARRANGE
    mock_repo_instance = MagicMock(spec=CostCalculatorRepository)
    mock_repo_instance.get_transaction_history.return_value = []
    mock_repo_instance.update_transaction_costs.return_value = DBTransaction(transaction_id="SELL01")

    mock_idempotency_repo = MagicMock(spec=IdempotencyRepository)
    mock_idempotency_repo.is_event_processed.return_value = False # It's a new event

    processed_sell_txn = EngineTransaction(transaction_id="SELL01", realized_gain_loss=Decimal("250.0"), portfolio_id="P1", instrument_id="I1", security_id="S1", transaction_type="SELL", transaction_date=datetime.now(), quantity=1, gross_transaction_amount=1, trade_currency="USD")
    mock_processor_instance = MagicMock()
    mock_processor_instance.process_transactions.return_value = ([processed_sell_txn], [])

    mock_db_session = MagicMock()
    mock_db_session.begin.return_value.__enter__.return_value = None

    # ACT
    with patch.object(cost_calculator_consumer, '_get_transaction_processor', return_value=mock_processor_instance), \
         patch("services.calculators.cost_calculator_service.app.consumer.get_db_session", return_value=iter([mock_db_session])), \
         patch("services.calculators.cost_calculator_service.app.consumer.CostCalculatorRepository", return_value=mock_repo_instance), \
         patch("services.calculators.cost_calculator_service.app.consumer.IdempotencyRepository", return_value=mock_idempotency_repo):

        cost_calculator_consumer._process_message(mock_kafka_message)

    # ASSERT
    mock_idempotency_repo.is_event_processed.assert_called_once()
    mock_repo_instance.get_transaction_history.assert_called_once()
    mock_repo_instance.update_transaction_costs.assert_called_once()
    mock_idempotency_repo.mark_event_processed.assert_called_once()
    cost_calculator_consumer._producer.publish_message.assert_called_once()

def test_process_message_skips_processed_event(cost_calculator_consumer: CostCalculatorConsumer, mock_kafka_message: MagicMock):
    """
    GIVEN a transaction message that has already been processed
    WHEN the process_message method is called
    THEN it should skip all business logic.
    """
    # ARRANGE
    mock_repo_instance = MagicMock(spec=CostCalculatorRepository)
    mock_idempotency_repo = MagicMock(spec=IdempotencyRepository)
    mock_idempotency_repo.is_event_processed.return_value = True # It's a DUPLICATE event

    mock_processor_instance = MagicMock()

    mock_db_session = MagicMock()
    mock_db_session.begin.return_value.__enter__.return_value = None

    # ACT
    with patch.object(cost_calculator_consumer, '_get_transaction_processor', return_value=mock_processor_instance), \
         patch("services.calculators.cost_calculator_service.app.consumer.get_db_session", return_value=iter([mock_db_session])), \
         patch("services.calculators.cost_calculator_service.app.consumer.CostCalculatorRepository", return_value=mock_repo_instance), \
         patch("services.calculators.cost_calculator_service.app.consumer.IdempotencyRepository", return_value=mock_idempotency_repo):

        cost_calculator_consumer._process_message(mock_kafka_message)

    # ASSERT
    mock_idempotency_repo.is_event_processed.assert_called_once()
    # Verify no other calls were made
    mock_repo_instance.get_transaction_history.assert_not_called()
    mock_processor_instance.process_transactions.assert_not_called()
    mock_repo_instance.update_transaction_costs.assert_not_called()
    mock_idempotency_repo.mark_event_processed.assert_not_called()
    cost_calculator_consumer._producer.publish_message.assert_not_called()