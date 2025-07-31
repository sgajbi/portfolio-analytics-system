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

def test_process_message_with_existing_history(cost_calculator_consumer: CostCalculatorConsumer):
    """
    GIVEN a new SELL transaction message for a security with a prior BUY
    WHEN the process_message method is called
    THEN it should use the repository, call the processor, update the DB, and publish an event.
    """
    # 1. ARRANGE
    portfolio_id = "PORT_COST_01"
    security_id = "SEC_COST_01"

    # CORRECTED: This mock DB object now has all the necessary fields
    existing_buy_txn_db = DBTransaction(
        transaction_id="BUY01", portfolio_id=portfolio_id, instrument_id="AAPL",
        security_id=security_id, transaction_date=datetime(2025, 1, 10),
        transaction_type="BUY", quantity=Decimal("10"), price=Decimal("150.0"),
        gross_transaction_amount=Decimal("1500.0"), net_cost=Decimal("1500.0"),
        trade_currency="USD", currency="USD"
    )

    new_sell_event = TransactionEvent(
        transaction_id="SELL01", portfolio_id=portfolio_id, instrument_id="AAPL",
        security_id=security_id, transaction_date=datetime(2025, 1, 20),
        transaction_type="SELL", quantity=Decimal("10"), price=Decimal("175.0"),
        gross_transaction_amount=Decimal("1750.0"), trade_currency="USD", currency="USD"
    )
    mock_kafka_message = MagicMock()
    mock_kafka_message.value.return_value = new_sell_event.model_dump_json().encode('utf-8')
    mock_kafka_message.headers.return_value = None

    # Mock the TransactionProcessor to return a pre-calculated result
    processed_sell_txn = EngineTransaction(**new_sell_event.model_dump())
    processed_sell_txn.realized_gain_loss = Decimal("250.0")
    mock_processor_instance = MagicMock()
    mock_processor_instance.process_transactions.return_value = ([processed_sell_txn], [])

    # Mock the Repository and its methods
    mock_repo_instance = MagicMock(spec=CostCalculatorRepository)
    mock_repo_instance.get_transaction_history.return_value = [existing_buy_txn_db]
    mock_repo_instance.update_transaction_costs.return_value = DBTransaction(**new_sell_event.model_dump())

    # 2. ACT
    with patch.object(cost_calculator_consumer, '_get_transaction_processor', return_value=mock_processor_instance), \
         patch("services.calculators.cost_calculator_service.app.consumer.get_db_session"), \
         patch("services.calculators.cost_calculator_service.app.consumer.CostCalculatorRepository", return_value=mock_repo_instance):

        cost_calculator_consumer._process_message(mock_kafka_message)

    # 3. ASSERT
    # Assert the repository was used to fetch history
    mock_repo_instance.get_transaction_history.assert_called_once()
    
    # Assert the repository was called to update the transaction
    mock_repo_instance.update_transaction_costs.assert_called_once()

    # Assert the producer was called to publish the final event
    mock_producer = cost_calculator_consumer._producer
    mock_producer.publish_message.assert_called_once()
    publish_args = mock_producer.publish_message.call_args.kwargs
    assert publish_args['value']['realized_gain_loss'] == "250.0"