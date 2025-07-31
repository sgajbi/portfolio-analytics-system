# services/calculators/position_calculator/tests/unit/consumers/test_transaction_event_consumer.py
import pytest
from unittest.mock import MagicMock, patch, ANY
from datetime import datetime, date
from decimal import Decimal

from portfolio_common.events import TransactionEvent
from portfolio_common.database_models import PositionHistory, Transaction as DBTransaction
from services.calculators.position_calculator.app.consumers.transaction_event_consumer import TransactionEventConsumer

# REMOVED: This test is not asynchronous
# pytestmark = pytest.mark.asyncio

@pytest.fixture
def position_consumer():
    """Provides an instance of the consumer with a mocked producer."""
    consumer = TransactionEventConsumer(
        bootstrap_servers="mock_server",
        topic="processed_transactions_completed",
        group_id="test_group"
    )
    consumer._producer = MagicMock()
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
    
    back_dated_event = TransactionEvent(
        transaction_id="TXN_DAY_2", portfolio_id=portfolio_id, security_id=security_id,
        transaction_date=datetime(2025, 8, 2), transaction_type="SELL", quantity=Decimal(20),
        net_cost=Decimal("-180"), instrument_id="NA", price=Decimal(9), gross_transaction_amount=Decimal(180), 
        trade_currency="USD", currency="USD", trade_fee=Decimal(0)
    )

    anchor_position = PositionHistory(
        portfolio_id=portfolio_id, security_id=security_id, position_date=date(2025, 8, 1),
        quantity=Decimal(100), cost_basis=Decimal(1000)
    )

    # CORRECTED: The mock DB object for Day 3 now includes all required fields
    txn_day_3 = DBTransaction(
        transaction_id="TXN_DAY_3", portfolio_id=portfolio_id, security_id=security_id,
        transaction_date=datetime(2025, 8, 3), transaction_type="BUY", quantity=Decimal(50),
        net_cost=Decimal("550"), instrument_id="NA", price=Decimal(11), gross_transaction_amount=Decimal(550), 
        trade_currency="USD", currency="USD", trade_fee=Decimal(0)
    )
    
    mock_repo = MagicMock()
    mock_repo.get_last_position_before.return_value = anchor_position
    mock_repo.get_transactions_on_or_after.return_value = [
        DBTransaction(**back_dated_event.model_dump()),
        txn_day_3
    ]

    mock_db_session = MagicMock()

    # 2. ACT
    with patch("services.calculators.position_calculator.app.consumers.transaction_event_consumer.get_db_session", return_value=iter([mock_db_session])), \
         patch("services.calculators.position_calculator.app.consumers.transaction_event_consumer.PositionRepository", return_value=mock_repo):
        
        position_consumer._recalculate_position_history(back_dated_event)

    # 3. ASSERT
    mock_repo.get_last_position_before.assert_called_once_with(
        portfolio_id=portfolio_id, security_id=security_id, a_date=date(2025, 8, 2)
    )
    mock_repo.delete_positions_from.assert_called_once_with(
        portfolio_id=portfolio_id, security_id=security_id, a_date=date(2025, 8, 2)
    )
    mock_repo.get_transactions_on_or_after.assert_called_once_with(
        portfolio_id=portfolio_id, security_id=security_id, a_date=date(2025, 8, 2)
    )

    assert mock_db_session.add.call_count == 2
    mock_db_session.commit.assert_called_once()
    
    assert position_consumer._producer.publish_message.call_count == 2
    position_consumer._producer.flush.assert_called_once()