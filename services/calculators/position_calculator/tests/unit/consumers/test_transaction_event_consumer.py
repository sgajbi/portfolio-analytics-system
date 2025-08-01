# services/calculators/position_calculator/tests/unit/consumers/test_transaction_event_consumer.py
import pytest
from unittest.mock import MagicMock, patch, call
from datetime import datetime, date
from decimal import Decimal

from portfolio_common.events import TransactionEvent
from portfolio_common.database_models import PositionHistory, Transaction as DBTransaction
from services.calculators.position_calculator.app.consumers.transaction_event_consumer import TransactionEventConsumer

@pytest.fixture
def position_consumer():
    consumer = TransactionEventConsumer(
        bootstrap_servers="mock_server",
        topic="processed_transactions_completed",
        group_id="test_group"
    )
    consumer._producer = MagicMock()
    consumer._producer.flush = MagicMock()
    return consumer

@pytest.mark.asyncio
async def test_recalculate_for_back_dated_transaction(position_consumer: TransactionEventConsumer):
    # 1. ARRANGE
    portfolio_id = "PORT_POS_01"
    security_id = "SEC_POS_01"
    
    back_dated_event = TransactionEvent(
        transaction_id="TXN_DAY_2", portfolio_id=portfolio_id, security_id=security_id,
        transaction_date=datetime(2025, 8, 2), transaction_type="SELL", quantity=Decimal(20),
        net_cost=Decimal("-180"), instrument_id="NA", price=Decimal(9), gross_transaction_amount=Decimal(180), 
        trade_currency="USD", currency="USD", trade_fee=Decimal(0)
    )
    mock_kafka_message = MagicMock()
    mock_kafka_message.value.return_value = back_dated_event.model_dump_json().encode('utf-8')
    mock_kafka_message.key.return_value = portfolio_id.encode('utf-8')
    mock_kafka_message.error.return_value = None
    mock_kafka_message.headers.return_value = None

    anchor_position = PositionHistory(
        portfolio_id=portfolio_id, security_id=security_id, position_date=date(2025, 8, 1),
        quantity=Decimal(100), cost_basis=Decimal(1000)
    )

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
    
    # CORRECTED MOCK: Simulate the commit populating the IDs on the objects
    def mock_commit():
        # Get all objects that were passed to `db.add()`
        added_records = [c.args[0] for c in mock_db_session.add.call_args_list]
        for i, record in enumerate(added_records, 1):
            record.id = i
    mock_db_session.commit.side_effect = mock_commit

    # 2. ACT
    with patch("services.calculators.position_calculator.app.consumers.transaction_event_consumer.get_db_session", return_value=iter([mock_db_session])), \
         patch("services.calculators.position_calculator.app.consumers.transaction_event_consumer.PositionRepository", return_value=mock_repo):
        
        await position_consumer.process_message(mock_kafka_message)

    # 3. ASSERT
    assert mock_db_session.add.call_count == 2
    mock_db_session.commit.assert_called_once()
    assert position_consumer._producer.publish_message.call_count == 2
    position_consumer._producer.flush.assert_called_once()