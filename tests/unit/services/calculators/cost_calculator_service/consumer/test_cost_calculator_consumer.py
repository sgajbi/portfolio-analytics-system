# tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_consumer.py
import pytest
import json
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime
from decimal import Decimal


from sqlalchemy.ext.asyncio import AsyncSession
from portfolio_common.events import TransactionEvent
from portfolio_common.database_models import Transaction as DBTransaction, Portfolio
from src.services.calculators.cost_calculator_service.app.consumer import CostCalculatorConsumer, PortfolioNotFoundError
from src.services.calculators.cost_calculator_service.app.repository import CostCalculatorRepository
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.outbox_repository import OutboxRepository
from core.models.transaction import Transaction as EngineTransaction
from core.models.transaction import Fees

pytestmark = pytest.mark.asyncio

@pytest.fixture
def cost_calculator_consumer():
    """
    Provides an instance of the consumer.
    """
    consumer = CostCalculatorConsumer(
        bootstrap_servers="mock_server",
        topic="raw_transactions_completed",
        group_id="test_group"
    )
    consumer._send_to_dlq_async = AsyncMock()
    return consumer

@pytest.fixture
def mock_dependencies():
    """A fixture to patch all external dependencies for a consumer test."""
    mock_repo = AsyncMock(spec=CostCalculatorRepository)
    mock_idempotency_repo = AsyncMock(spec=IdempotencyRepository)
    mock_outbox_repo = AsyncMock(spec=OutboxRepository)
    
    mock_db_session = AsyncMock(spec=AsyncSession)
    mock_transaction = AsyncMock()
    mock_db_session.begin.return_value = mock_transaction
    
    async def get_session_gen():
        yield mock_db_session

    with patch("src.services.calculators.cost_calculator_service.app.consumer.get_async_db_session", new=get_session_gen), \
         patch("src.services.calculators.cost_calculator_service.app.consumer.CostCalculatorRepository", return_value=mock_repo), \
         patch("src.services.calculators.cost_calculator_service.app.consumer.IdempotencyRepository", return_value=mock_idempotency_repo), \
         patch("src.services.calculators.cost_calculator_service.app.consumer.OutboxRepository", return_value=mock_outbox_repo):
        yield {
            "repo": mock_repo,
            "idempotency_repo": mock_idempotency_repo,
            "outbox_repo": mock_outbox_repo
        }

@pytest.fixture
def mock_sell_kafka_message():
    """Provides a reusable mock Kafka message for a SELL transaction."""
    sell_event = TransactionEvent(
        transaction_id="SELL01", portfolio_id="PORT_COST_01", instrument_id="AAPL",
        security_id="SEC_COST_01", transaction_date=datetime(2025, 1, 20),
        transaction_type="SELL", quantity=Decimal("10"), price=Decimal("175.0"),
        gross_transaction_amount=Decimal("1750.0"), trade_currency="USD", currency="USD",
        trade_fee=Decimal("0.0")
    )
    mock_msg = MagicMock()
    mock_msg.value.return_value = sell_event.model_dump_json().encode('utf-8')
    mock_msg.topic.return_value = "raw_transactions_completed"
    mock_msg.partition.return_value = 0
    mock_msg.offset.return_value = 1
    mock_msg.headers.return_value = []
    return mock_msg

@pytest.fixture
def mock_buy_kafka_message() -> MagicMock:
    """Creates a mock Kafka message for a BUY transaction with a fee."""
    buy_event = TransactionEvent(
        transaction_id="BUY_WITH_FEE_01", portfolio_id="PORT_COST_01", instrument_id="AAPL",
        security_id="SEC_COST_01", transaction_date=datetime(2025, 1, 15),
        transaction_type="BUY", quantity=Decimal("10"), price=Decimal("150.0"),
        gross_transaction_amount=Decimal("1500.0"), trade_fee=Decimal("7.50"),
        trade_currency="USD", currency="USD",
    )
    mock_msg = MagicMock()
    mock_msg.value.return_value = buy_event.model_dump_json().encode('utf-8')
    mock_msg.topic.return_value = "raw_transactions_completed"
    mock_msg.partition.return_value = 0
    mock_msg.offset.return_value = 2
    mock_msg.headers.return_value = []
    return mock_msg

async def test_consumer_integration_with_engine(cost_calculator_consumer: CostCalculatorConsumer, mock_sell_kafka_message: MagicMock, mock_dependencies):
    """
    GIVEN a new SELL transaction message
    WHEN the consumer processes it, using the real TransactionProcessor
    THEN it should fetch history, calculate the realized P&L, and update the database.
    """
    # ARRANGE
    mock_repo = mock_dependencies["repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]
    mock_outbox_repo = mock_dependencies["outbox_repo"]

    buy_history = DBTransaction(
        transaction_id="BUY01", portfolio_id="PORT_COST_01", security_id="SEC_COST_01",
        instrument_id="AAPL", transaction_type="BUY", transaction_date=datetime(2025, 1, 10),
        quantity=Decimal("10"), price=Decimal("150.0"), gross_transaction_amount=Decimal("1500.0"),
        trade_currency="USD", currency="USD", net_cost=Decimal("1500"), net_cost_local=Decimal("1500"),
        transaction_fx_rate=Decimal("1.0"), trade_fee=Decimal("0.0")
    )
    mock_repo.get_transaction_history.return_value = [buy_history]
    mock_repo.get_portfolio.return_value = Portfolio(base_currency="USD", portfolio_id="PORT_COST_01")
    mock_repo.get_fx_rate.return_value = None
    mock_idempotency_repo.is_event_processed.return_value = False

    def create_db_tx(engine_txn: EngineTransaction) -> DBTransaction:
        data = engine_txn.model_dump(exclude_none=True)
        data.pop('portfolio_base_currency', None)
        data.pop('fees', None)
        data.pop('accrued_interest', None)
        data.pop('epoch', None)
        data.pop('net_transaction_amount', None)
        data.pop('average_price', None)
        data.pop('error_reason', None)
        return DBTransaction(**data)
    mock_repo.update_transaction_costs.side_effect = create_db_tx

    # ACT
    await cost_calculator_consumer.process_message(mock_sell_kafka_message)

    # ASSERT
    mock_idempotency_repo.is_event_processed.assert_called_once()
    mock_repo.get_transaction_history.assert_called_once()
    updated_transaction_arg = mock_repo.update_transaction_costs.call_args[0][0]
    assert isinstance(updated_transaction_arg, EngineTransaction)
    assert updated_transaction_arg.realized_gain_loss == Decimal("250.0")
    mock_idempotency_repo.mark_event_processed.assert_called_once()
    mock_outbox_repo.create_outbox_event.assert_called_once()

async def test_consumer_uses_trade_fee_in_calculation(
    cost_calculator_consumer: CostCalculatorConsumer, mock_buy_kafka_message: MagicMock, mock_dependencies
):
    """
    GIVEN a new BUY transaction message with a trade_fee
    WHEN the consumer processes it using the real engine
    THEN the final updated transaction should have a net_cost that includes the fee.
    """
    # ARRANGE
    mock_repo = mock_dependencies["repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]
    
    mock_idempotency_repo.is_event_processed.return_value = False
    mock_repo.get_transaction_history.return_value = []
    mock_repo.get_portfolio.return_value = Portfolio(base_currency="USD", portfolio_id="PORT_COST_01")
    mock_repo.get_fx_rate.return_value = None
    mock_repo.update_transaction_costs.side_effect = lambda arg: arg

    # ACT
    await cost_calculator_consumer.process_message(mock_buy_kafka_message)

    # ASSERT
    mock_repo.update_transaction_costs.assert_called_once()
    updated_transaction_arg = mock_repo.update_transaction_costs.call_args[0][0]
    
    assert updated_transaction_arg.net_cost == Decimal("1507.50")

async def test_consumer_propagates_epoch_field(
    cost_calculator_consumer: CostCalculatorConsumer, mock_buy_kafka_message: MagicMock, mock_dependencies
):
    """
    GIVEN an incoming transaction event with an epoch
    WHEN the consumer processes it
    THEN the outbound event it creates should also contain that same epoch.
    """
    # ARRANGE
    mock_repo = mock_dependencies["repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]
    mock_outbox_repo = mock_dependencies["outbox_repo"]
    
    incoming_event_dict = mock_buy_kafka_message.value().decode('utf-8')
    incoming_event_dict = json.loads(incoming_event_dict)
    incoming_event_dict['epoch'] = 2
    mock_buy_kafka_message.value.return_value = json.dumps(incoming_event_dict).encode('utf-8')

    mock_idempotency_repo.is_event_processed.return_value = False
    mock_repo.get_transaction_history.return_value = []
    mock_repo.get_portfolio.return_value = Portfolio(base_currency="USD", portfolio_id="PORT_COST_01")
    mock_repo.get_fx_rate.return_value = None
    
    exclude_fields = {
        'portfolio_base_currency', 'fees', 'accrued_interest', 'epoch', 
        'net_transaction_amount', 'average_price', 'error_reason'
    }
    mock_repo.update_transaction_costs.side_effect = lambda arg: DBTransaction(
        **arg.model_dump(exclude=exclude_fields)
    )

    # ACT
    await cost_calculator_consumer.process_message(mock_buy_kafka_message)

    # ASSERT
    mock_outbox_repo.create_outbox_event.assert_called_once()
    outbound_payload = mock_outbox_repo.create_outbox_event.call_args.kwargs['payload']
    assert outbound_payload['epoch'] == 2

async def test_consumer_retries_when_portfolio_not_found(
    cost_calculator_consumer: CostCalculatorConsumer, mock_buy_kafka_message: MagicMock, mock_dependencies
):
    """
    GIVEN a transaction message
    WHEN the corresponding portfolio is not found on the first attempt
    THEN the consumer should raise PortfolioNotFoundError to trigger a retry.
    """
    # ARRANGE
    mock_repo = mock_dependencies["repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]
    
    mock_idempotency_repo.is_event_processed.return_value = False
    # Simulate portfolio not found
    mock_repo.get_portfolio.return_value = None

    # ACT & ASSERT
    with pytest.raises(PortfolioNotFoundError):
        await cost_calculator_consumer.process_message(mock_buy_kafka_message)

    # --- FIX: Verify it was awaited, not how many times ---
    mock_repo.get_portfolio.assert_awaited()
    assert mock_repo.get_portfolio.await_count > 1
    # --- END FIX ---
    mock_repo.get_transaction_history.assert_not_called()