# tests/unit/services/calculators/cost_calculator_service/consumer/test_consumer.py
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime
from decimal import Decimal

from portfolio_common.events import TransactionEvent
from portfolio_common.database_models import Transaction as DBTransaction, Portfolio
from portfolio_common.config import KAFKA_PROCESSED_TRANSACTIONS_COMPLETED_TOPIC
from core.models.transaction import Transaction as EngineTransaction
from src.services.calculators.cost_calculator_service.app.consumer import CostCalculatorConsumer
from src.services.calculators.cost_calculator_service.app.repository import CostCalculatorRepository
from portfolio_common.idempotency_repository import IdempotencyRepository

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
    mock_msg.headers.return_value = []
    return mock_msg

async def test_process_message_with_existing_history(cost_calculator_consumer: CostCalculatorConsumer, mock_kafka_message: MagicMock):
    """
    GIVEN a new transaction message
    WHEN the process_message method is called
    THEN it should process the event, update the DB, and publish to the outbox.
    """
    # ARRANGE
    mock_repo_instance = AsyncMock(spec=CostCalculatorRepository)
    mock_repo_instance.get_transaction_history.return_value = []
    mock_repo_instance.update_transaction_costs.return_value = DBTransaction(transaction_id="SELL01")
    mock_repo_instance.get_portfolio.return_value = Portfolio(base_currency="USD")
    mock_repo_instance.get_fx_rate.return_value = None

    mock_idempotency_repo = AsyncMock(spec=IdempotencyRepository)
    mock_idempotency_repo.is_event_processed.return_value = False

    mock_outbox_repo = MagicMock()

    processed_sell_txn = EngineTransaction(
        transaction_id="SELL01", realized_gain_loss=Decimal("250.0"), portfolio_id="P1",
        instrument_id="I1", security_id="S1", transaction_type="SELL", transaction_date=datetime.now(),
        quantity=1, gross_transaction_amount=1, trade_currency="USD", portfolio_base_currency="USD"
    )
    mock_processor_instance = MagicMock()
    mock_processor_instance.process_transactions.return_value = ([processed_sell_txn], [])

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
    mock_repo_instance.get_transaction_history.assert_called_once()
    mock_repo_instance.update_transaction_costs.assert_called_once()
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
    mock_outbox_repo = MagicMock()
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
    mock_processor_instance.process_transactions.assert_not_called()
    mock_outbox_repo.create_outbox_event.assert_not_called()