# tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_consumer.py
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime
from decimal import Decimal

from portfolio_common.events import TransactionEvent
from portfolio_common.database_models import Transaction as DBTransaction, Portfolio
from src.services.calculators.cost_calculator_service.app.consumer import CostCalculatorConsumer
from src.services.calculators.cost_calculator_service.app.repository import CostCalculatorRepository
from portfolio_common.idempotency_repository import IdempotencyRepository
from core.models.transaction import Transaction as EngineTransaction

pytestmark = pytest.mark.asyncio

@pytest.fixture
def cost_calculator_consumer():
    """Provides an instance of the consumer."""
    consumer = CostCalculatorConsumer(
        bootstrap_servers="mock_server",
        topic="raw_transactions_completed",
        group_id="test_group"
    )
    consumer._send_to_dlq_async = AsyncMock()
    return consumer

@pytest.fixture
def mock_kafka_message():
    """Provides a reusable mock Kafka message for a SELL transaction."""
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
    mock_msg.headers.return_value = []
    return mock_msg

async def test_consumer_integration_with_engine(cost_calculator_consumer: CostCalculatorConsumer, mock_kafka_message: MagicMock):
    """
    GIVEN a new SELL transaction message
    WHEN the consumer processes it, using the real TransactionProcessor
    THEN it should fetch history, calculate the realized P&L, and update the database.
    """
    # ARRANGE
    mock_repo_instance = AsyncMock(spec=CostCalculatorRepository)
    mock_idempotency_repo = AsyncMock(spec=IdempotencyRepository)
    mock_outbox_repo = AsyncMock() # <-- FIX: Use AsyncMock

    # Simulate the repository returning the previous BUY transaction history
    buy_history = DBTransaction(
        transaction_id="BUY01", portfolio_id="PORT_COST_01", security_id="SEC_COST_01",
        instrument_id="AAPL",
        transaction_type="BUY", transaction_date=datetime(2025, 1, 10),
        quantity=Decimal("10"), price=Decimal("150.0"), gross_transaction_amount=Decimal("1500.0"),
        trade_currency="USD", currency="USD", net_cost=Decimal("1500"), net_cost_local=Decimal("1500"),
        transaction_fx_rate=Decimal("1.0"),
        trade_fee=Decimal("0.0")
    )
    mock_repo_instance.get_transaction_history.return_value = [buy_history]
    mock_repo_instance.get_portfolio.return_value = Portfolio(base_currency="USD", portfolio_id="PORT_COST_01")
    mock_repo_instance.get_fx_rate.return_value = None

    mock_idempotency_repo.is_event_processed.return_value = False

    # FIX: Configure the mock to return a realistic DB object from the input it receives.
    def create_db_transaction_from_engine(engine_txn: EngineTransaction) -> DBTransaction:
        data = engine_txn.model_dump(exclude_none=True)
        data.pop('portfolio_base_currency', None)
        data.pop('fees', None)
        data.pop('accrued_interest', None) # <-- FIX: Remove the incompatible 'accrued_interest' field
        return DBTransaction(**data)

    mock_repo_instance.update_transaction_costs.side_effect = create_db_transaction_from_engine


    mock_db_session = AsyncMock()
    mock_db_session.begin.return_value = AsyncMock()
    async def mock_get_db_session_generator():
        yield mock_db_session

    # ACT
    with patch("src.services.calculators.cost_calculator_service.app.consumer.get_async_db_session", new=mock_get_db_session_generator), \
         patch("src.services.calculators.cost_calculator_service.app.consumer.CostCalculatorRepository", return_value=mock_repo_instance), \
         patch("src.services.calculators.cost_calculator_service.app.consumer.IdempotencyRepository", return_value=mock_idempotency_repo), \
         patch("src.services.calculators.cost_calculator_service.app.consumer.OutboxRepository", return_value=mock_outbox_repo):

        await cost_calculator_consumer.process_message(mock_kafka_message)

    # ASSERT
    mock_idempotency_repo.is_event_processed.assert_called_once()
    mock_repo_instance.get_transaction_history.assert_called_once()

    # Verify that the real engine was called and produced the correct result
    # PnL = (10 * 175) - (10 * 150) = 1750 - 1500 = 250
    mock_repo_instance.update_transaction_costs.assert_called_once()
    updated_transaction_arg = mock_repo_instance.update_transaction_costs.call_args[0][0]
    assert isinstance(updated_transaction_arg, EngineTransaction)
    assert updated_transaction_arg.realized_gain_loss == Decimal("250.0")

    mock_idempotency_repo.mark_event_processed.assert_called_once()
    mock_outbox_repo.create_outbox_event.assert_called_once()

async def test_process_message_skips_processed_event(cost_calculator_consumer: CostCalculatorConsumer, mock_kafka_message: MagicMock):
    """
    GIVEN a transaction message that has already been processed
    WHEN the process_message method is called
    THEN it should skip all business logic.
    """
    # ARRANGE
    mock_repo_instance = AsyncMock(spec=CostCalculatorRepository)
    mock_idempotency_repo = AsyncMock(spec=IdempotencyRepository)
    mock_idempotency_repo.is_event_processed.return_value = True
    mock_outbox_repo = AsyncMock() # <-- FIX: Use AsyncMock
    mock_processor_instance = MagicMock()

    mock_db_session = AsyncMock()
    mock_db_session.begin.return_value = AsyncMock()
    async def mock_get_db_session_generator():
        yield mock_db_session

    # ACT
    with patch.object(cost_calculator_consumer, '_get_transaction_processor', return_value=mock_processor_instance), \
         patch("src.services.calculators.cost_calculator_service.app.consumer.get_async_db_session", new=mock_get_db_session_generator), \
         patch("src.services.calculators.cost_calculator_service.app.consumer.CostCalculatorRepository", return_value=mock_repo_instance), \
         patch("src.services.calculators.cost_calculator_service.app.consumer.IdempotencyRepository", return_value=mock_idempotency_repo), \
         patch("src.services.calculators.cost_calculator_service.app.consumer.OutboxRepository", return_value=mock_outbox_repo):

        await cost_calculator_consumer.process_message(mock_kafka_message)

    # ASSERT
    mock_idempotency_repo.is_event_processed.assert_called_once()
    # The real processor should not be called because of the idempotency check
    mock_processor_instance.process_transactions.assert_not_called()
    mock_outbox_repo.create_outbox_event.assert_not_called()