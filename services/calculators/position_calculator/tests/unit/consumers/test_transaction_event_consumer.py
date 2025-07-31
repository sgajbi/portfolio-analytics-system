# services/calculators/position_calculator/tests/unit/consumers/test_transaction_event_consumer.py
import pytest
from unittest.mock import MagicMock, patch, ANY
from datetime import datetime, date
from decimal import Decimal

from portfolio_common.events import TransactionEvent
from portfolio_common.database_models import PositionHistory, Transaction as DBTransaction
from services.calculators.position_calculator.app.consumers.transaction_event_consumer import TransactionEventConsumer

# Mark all tests in this file as asyncio
pytestmark = pytest.mark.asyncio

@pytest.fixture
def position_consumer():
    """Provides an instance of the consumer with a mocked producer."""
    consumer = TransactionEventConsumer(
        bootstrap_servers="mock_server",
        topic="processed_transactions_completed",
        group_id="test_group"
    )
    consumer._producer = MagicMock()
    # The consumer's _recalculate method calls the producer's flush, mock it too
    consumer._producer.flush = MagicMock()
    return consumer

def test_recalculate_for_back_dated_transaction(position_consumer: TransactionEventConsumer):
    """
    GIVEN an existing position history for Day 1 and Day 3
    WHEN a new transaction for Day 2 arrives
    THEN the consumer should delete history from Day 2 onwards and correctly replay to recreate
    the history for Day 2 and Day 3.
    """
    # 1. ARRANGE
    portfolio_id = "PORT_POS_01"
    security_id = "SEC_POS_01"
    
    # The incoming back-dated transaction for Day 2
    back_dated_event = TransactionEvent(
        transaction_id="TXN_DAY_2", portfolio_id=portfolio_id, security_id=security_id,
        transaction_date=datetime(2025, 8, 2), transaction_type="SELL", quantity=Decimal(20),
        net_cost=Decimal("-180"), instrument_id="NA", price=0, gross_transaction_amount=0, trade_currency="USD", currency="USD"
    )
    mock_kafka_message = MagicMock()
    mock_kafka_message.value.return_value = back_dated_event.model_dump_json().encode('utf-8')
    mock_kafka_message.key.return_value = portfolio_id.encode('utf-8')
    mock_kafka_message.error.return_value = None

    # The anchor position from Day 1 that the logic should start from
    anchor_position = PositionHistory(
        portfolio_id=portfolio_id, security_id=security_id, position_date=date(2025, 8, 1),
        quantity=Decimal(100), cost_basis=Decimal(1000)
    )

    # The list of transactions to be replayed (the new Day 2 and existing Day 3)
    # The consumer will fetch these from the DB
    txn_day_3 = DBTransaction(
        transaction_id="TXN_DAY_3", portfolio_id=portfolio_id, security_id=security_id,
        transaction_date=datetime(2025, 8, 3), transaction_type="BUY", quantity=Decimal(50),
        net_cost=Decimal("550"), instrument_id="NA", price=0, gross_transaction_amount=0, trade_currency="USD", currency="USD"
    )
    
    # Mock the repository and its method return values
    mock_repo = MagicMock()
    mock_repo.get_last_position_before.return_value = anchor_position
    # Note: The consumer's logic re-fetches the incoming transaction from the DB along with others
    mock_repo.get_transactions_on_or_after.return_value = [
        DBTransaction(**back_dated_event.model_dump()), # The new txn for Day 2
        txn_day_3 # The existing txn for Day 3
    ]

    # Mock the database session
    mock_db_session = MagicMock()

    # 2. ACT
    with patch("services.calculators.position_calculator.app.consumers.transaction_event_consumer.get_db_session", return_value=iter([mock_db_session])), \
         patch("services.calculators.position_calculator.app.consumers.transaction_event_consumer.PositionRepository", return_value=mock_repo):
        
        position_consumer._recalculate_position_history(back_dated_event)

    # 3. ASSERT
    # Verify it found the correct anchor point
    mock_repo.get_last_position_before.assert_called_once_with(
        portfolio_id=portfolio_id, security_id=security_id, a_date=date(2025, 8, 2)
    )
    # Verify it deleted the correct stale records (from Day 2 onwards)
    mock_repo.delete_positions_from.assert_called_once_with(
        portfolio_id=portfolio_id, security_id=security_id, a_date=date(2025, 8, 2)
    )
    # Verify it fetched the correct set of transactions to replay
    mock_repo.get_transactions_on_or_after.assert_called_once_with(
        portfolio_id=portfolio_id, security_id=security_id, a_date=date(2025, 8, 2)
    )

    # Verify that two new PositionHistory records were added to the session
    assert mock_db_session.add.call_count == 2
    mock_db_session.commit.assert_called_once()
    
    # Verify that two completion events were published
    assert position_consumer._producer.publish_message.call_count == 2
    position_consumer._producer.flush.assert_called_once()