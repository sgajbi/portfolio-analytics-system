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

    existing_buy_txn = DBTransaction(
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

    # Mock the database session and its query results
    mock_db_session = MagicMock()

    # CORRECTED MOCK: Use side_effect to handle the two separate filter calls
    mock_query_chain = MagicMock()
    # Configure the first call (.all()) to return the history
    mock_query_chain.filter.return_value.all.return_value = [existing_buy_txn]
    # Configure the second call (.first()) to return the object to be updated
    mock_query_chain.filter.return_value.first.return_value = DBTransaction(**new_sell_event.model_dump())
    mock_db_session.query.return_value = mock_query_chain

    # 2. ACT
    with patch(
        "services.calculators.cost_calculator_service.app.consumer.get_db_session",
        return_value=iter([mock_db_session])
    ):
        cost_calculator_consumer._process_message(mock_kafka_message)

    # 3. ASSERT
    # Assert that the filter method was called twice (once for history, once for update)
    assert mock_query_chain.filter.call_count == 2

    # Assert that the transaction in the session was updated with the gain/loss
    updated_txn_in_session = mock_query_chain.filter.return_value.first.return_value
    assert updated_txn_in_session.realized_gain_loss == Decimal("250")

    # Assert that the session was committed
    mock_db_session.commit.assert_called_once()
    
    # Assert that the completion event was published
    mock_producer = cost_calculator_consumer._producer
    mock_producer.publish_message.assert_called_once()

    publish_args = mock_producer.publish_message.call_args.kwargs
    assert publish_args['value']['realized_gain_loss'] == "250.0000000000"