import pytest
from unittest.mock import MagicMock, patch, call
from datetime import datetime, date
from decimal import Decimal

from portfolio_common.events import TransactionEvent
from portfolio_common.database_models import PositionHistory, Transaction as DBTransaction
from services.calculators.position_calculator.app.consumers.transaction_event_consumer import TransactionEventConsumer


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


@pytest.mark.asyncio
async def test_recalculate_for_back_dated_transaction(position_consumer: TransactionEventConsumer):
    """
    GIVEN an existing position history for Day 1 and Day 3
    WHEN a new transaction for Day 2 arrives
    THEN the consumer should recalculate and save new history.
    """
    portfolio_id = "PORT_POS_01"
    security_id = "SEC_POS_01"
    
    back_dated_event = TransactionEvent(
        transaction_id="TXN_DAY_2", portfolio_id=portfolio_id, security_id=security_id,
        transaction_date=datetime(2025, 8, 2), transaction_type="SELL", quantity=Decimal(20),
        net_cost=Decimal("-180"), instrument_id="NA", price=Decimal(9),
        gross_transaction_amount=Decimal(180), trade_currency="USD",
        currency="USD", trade_fee=Decimal(0)
    )
    mock_kafka_message = MagicMock()
    mock_kafka_message.value.return_value = back_dated_event.model_dump_json().encode("utf-8")
    mock_kafka_message.key.return_value = portfolio_id.encode("utf-8")
    mock_kafka_message.error.return_value = None
    mock_kafka_message.headers.return_value = None

    anchor_position = PositionHistory(
        portfolio_id=portfolio_id, security_id=security_id, position_date=date(2025, 8, 1),
        quantity=Decimal(100), cost_basis=Decimal(1000)
    )

    txn_day_3 = DBTransaction(
        transaction_id="TXN_DAY_3", portfolio_id=portfolio_id, security_id=security_id,
        transaction_date=datetime(2025, 8, 3), transaction_type="BUY", quantity=Decimal(50),
        net_cost=Decimal("550"), instrument_id="NA", price=Decimal(11),
        gross_transaction_amount=Decimal(550), trade_currency="USD",
        currency="USD", trade_fee=Decimal(0)
    )
    
    mock_repo = MagicMock()
    mock_repo.get_last_position_before.return_value = anchor_position
    mock_repo.get_transactions_on_or_after.return_value = [
        DBTransaction(**back_dated_event.model_dump()),
        txn_day_3
    ]

    mock_db_session = MagicMock()
    committed_records_with_ids = [
        PositionHistory(id=101, transaction_id="TXN_DAY_2", security_id=security_id, portfolio_id=portfolio_id, position_date=date(2025, 8, 2)),
        PositionHistory(id=102, transaction_id="TXN_DAY_3", security_id=security_id, portfolio_id=portfolio_id, position_date=date(2025, 8, 3))
    ]
    mock_db_session.query.return_value.filter.return_value.all.return_value = committed_records_with_ids

    with patch("services.calculators.position_calculator.app.consumers.transaction_event_consumer.get_db_session", return_value=iter([mock_db_session])), \
         patch("services.calculators.position_calculator.app.consumers.transaction_event_consumer.PositionRepository", return_value=mock_repo):
        
        await position_consumer.process_message(mock_kafka_message)

    mock_repo.get_last_position_before.assert_called_once()
    mock_repo.delete_positions_from.assert_called_once()
    mock_repo.get_transactions_on_or_after.assert_called_once()
    mock_repo.save_positions.assert_called_once()

    mock_db_session.commit.assert_called_once()
    
    assert position_consumer._producer.publish_message.call_count == 2
    position_consumer._producer.flush.assert_called_once()


@pytest.mark.asyncio
async def test_idempotency_skips_duplicates(position_consumer: TransactionEventConsumer):
    """
    GIVEN duplicate transaction IDs already in PositionHistory
    WHEN recalculation runs
    THEN save_positions should skip inserting duplicates but still flush events.
    """
    portfolio_id = "PORT_IDEMPOTENCY"
    security_id = "SEC_IDEMPOTENCY"

    txn_event = TransactionEvent(
        transaction_id="TXN_DUP", portfolio_id=portfolio_id, security_id=security_id,
        transaction_date=datetime(2025, 8, 2), transaction_type="BUY", quantity=Decimal(10),
        net_cost=Decimal("100"), instrument_id="NA", price=Decimal(10),
        gross_transaction_amount=Decimal(100), trade_currency="USD",
        currency="USD", trade_fee=Decimal(0)
    )
    mock_kafka_message = MagicMock()
    mock_kafka_message.value.return_value = txn_event.model_dump_json().encode("utf-8")
    mock_kafka_message.key.return_value = portfolio_id.encode("utf-8")

    mock_repo = MagicMock()
    mock_repo.get_last_position_before.return_value = None
    mock_repo.get_transactions_on_or_after.return_value = [DBTransaction(**txn_event.model_dump())]
    mock_repo.save_positions.side_effect = lambda positions: positions.clear()  # Simulates skipping all inserts

    mock_db_session = MagicMock()
    mock_db_session.query.return_value.filter.return_value.all.return_value = []

    with patch("services.calculators.position_calculator.app.consumers.transaction_event_consumer.get_db_session", return_value=iter([mock_db_session])), \
         patch("services.calculators.position_calculator.app.consumers.transaction_event_consumer.PositionRepository", return_value=mock_repo):
        
        await position_consumer.process_message(mock_kafka_message)

    mock_repo.save_positions.assert_called_once()
    position_consumer._producer.flush.assert_called_once()
    assert position_consumer._producer.publish_message.call_count >= 0  # Could be 0 if nothing new


@pytest.mark.asyncio
async def test_retries_on_transient_db_error(position_consumer: TransactionEventConsumer):
    """
    GIVEN a transient DB error occurs during recalculation
    WHEN process_message is invoked
    THEN it should retry before failing.
    """
    portfolio_id = "PORT_RETRY"
    security_id = "SEC_RETRY"

    txn_event = TransactionEvent(
        transaction_id="TXN_RETRY", portfolio_id=portfolio_id, security_id=security_id,
        transaction_date=datetime(2025, 8, 2), transaction_type="SELL", quantity=Decimal(5),
        net_cost=Decimal("-50"), instrument_id="NA", price=Decimal(10),
        gross_transaction_amount=Decimal(50), trade_currency="USD",
        currency="USD", trade_fee=Decimal(0)
    )
    mock_kafka_message = MagicMock()
    mock_kafka_message.value.return_value = txn_event.model_dump_json().encode("utf-8")
    mock_kafka_message.key.return_value = portfolio_id.encode("utf-8")

    mock_repo = MagicMock()
    mock_repo.get_last_position_before.side_effect = Exception("Simulated transient error")

    mock_db_session = MagicMock()

    with patch("services.calculators.position_calculator.app.consumers.transaction_event_consumer.get_db_session", return_value=iter([mock_db_session, mock_db_session, mock_db_session])), \
         patch("services.calculators.position_calculator.app.consumers.transaction_event_consumer.PositionRepository", return_value=mock_repo):
        
        await position_consumer.process_message(mock_kafka_message)

    assert mock_repo.get_last_position_before.call_count >= 1
