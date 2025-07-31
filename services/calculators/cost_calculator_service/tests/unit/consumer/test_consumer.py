# services/calculators/cost_calculator_service/tests/unit/consumer/test_consumer.py
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
from decimal import Decimal

from portfolio_common.events import TransactionEvent
from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.config import KAFKA_PROCESSED_TRANSACTIONS_COMPLETED_TOPIC
from services.calculators.cost_calculator_service.app.consumer import CostCalculatorConsumer

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
    THEN it should fetch history, calculate gain/loss, update the DB, and publish an event.
    """
    # 1. ARRANGE
    portfolio_id = "PORT_COST_01"
    security_id = "SEC_COST_01"

    # Represent the existing transaction already in the database
    existing_buy_txn = DBTransaction(
        transaction_id="BUY01",
        portfolio_id=portfolio_id,
        instrument_id="AAPL",
        security_id=security_id,
        transaction_date=datetime(2025, 1, 10),
        transaction_type="BUY",
        quantity=Decimal("10"),
        price=Decimal("150.0"),
        gross_transaction_amount=Decimal("1500.0"),
        net_cost=Decimal("1500.0"), # Previously calculated
        trade_currency="USD",
        currency="USD"
    )

    # Represent the new transaction arriving from Kafka
    new_sell_event = TransactionEvent(
        transaction_id="SELL01",
        portfolio_id=portfolio_id,
        instrument_id="AAPL",
        security_id=security_id,
        transaction_date=datetime(2025, 1, 20),
        transaction_type="SELL",
        quantity=Decimal("10"),
        price=Decimal("175.0"),
        gross_transaction_amount=Decimal("1750.0"),
        trade_currency="USD",
        currency="USD"
    )
    mock_kafka_message = MagicMock()
    mock_kafka_message.value.return_value = new_sell_event.model_dump_json().encode('utf-8')

    # Mock the database session and its query results
    mock_db_session = MagicMock()
    # Mock the query to find existing transactions
    mock_db_session.query.return_value.filter.return_value.all.return_value = [existing_buy_txn]
    # Mock the query to find the transaction to update
    mock_db_session.query.return_value.filter.return_value.first.return_value = DBTransaction(**new_sell_event.model_dump())

    # 2. ACT
    with patch(
        "services.calculators.cost_calculator_service.app.consumer.get_db_session",
        # CORRECTED: Return an iterator to correctly mock the generator
        return_value=iter([mock_db_session])
    ):
        cost_calculator_consumer._process_message(mock_kafka_message)

    # 3. ASSERT
    # Assert that the database was queried to get the history
    mock_db_session.query.return_value.filter.assert_called()

    # Assert that the transaction in the session was updated with the gain/loss
    # Expected Gain = 1750 (proceeds) - 1500 (cost basis) = 250
    updated_txn_in_session = mock_db_session.query.return_value.filter.return_value.first.return_value
    assert updated_txn_in_session.realized_gain_loss == Decimal("250")

    # Assert that the session was committed
    mock_db_session.commit.assert_called_once()
    
    # Assert that the completion event was published
    mock_producer = cost_calculator_consumer._producer
    mock_producer.publish_message.assert_called_once()

    publish_args = mock_producer.publish_message.call_args.kwargs
    assert publish_args['topic'] == KAFKA_PROCESSED_TRANSACTIONS_COMPLETED_TOPIC
    assert publish_args['key'] == portfolio_id
    assert publish_args['value']['transaction_id'] == "SELL01"
    assert publish_args['value']['realized_gain_loss'] == "250.0000000000"