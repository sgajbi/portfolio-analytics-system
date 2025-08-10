# services/calculators/position-valuation-calculator/tests/unit/consumers/test_valuation_market_price_consumer.py
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
# Corrected imports using underscores for the package name
from services.calculators.position_valuation_calculator.app.consumers.market_price_consumer import MarketPriceConsumer
from portfolio_common.events import MarketPriceEvent
from portfolio_common.database_models import DailyPositionSnapshot, Portfolio, Instrument

pytestmark = pytest.mark.asyncio

@pytest.fixture
def consumer():
    """Provides a clean instance of the MarketPriceConsumer."""
    c = MarketPriceConsumer(
        bootstrap_servers="mock_server",
        topic="market_price_persisted",
        group_id="test_group",
    )
    c._send_to_dlq_async = AsyncMock()
    return c

@pytest.fixture
def mock_event():
    """Provides a consistent MarketPriceEvent for tests."""
    return MarketPriceEvent(
        security_id="SEC_PRICE_01",
        price_date=date(2025, 8, 5),
        price=Decimal("200.00"),
        currency="USD"
    )

@pytest.fixture
def mock_kafka_message(mock_event: MarketPriceEvent):
    """Creates a mock Kafka message from the event."""
    mock_msg = MagicMock()
    mock_msg.value.return_value = mock_event.model_dump_json().encode('utf-8')
    mock_msg.key.return_value = "test_key".encode('utf-8')
    mock_msg.topic.return_value = "market_price_persisted"
    mock_msg.partition.return_value = 0
    mock_msg.offset.return_value = 10
    mock_msg.error.return_value = None
    mock_msg.headers.return_value = []
    return mock_msg

async def test_process_message_success_and_keys_by_portfolio_id(consumer: MarketPriceConsumer, mock_kafka_message: MagicMock, mock_event: MarketPriceEvent):
    """
    GIVEN a new market price event for a security held in a portfolio
    WHEN the consumer processes the message
    THEN it should update the snapshot and publish an outbox event keyed by portfolio_id.
    """
    # Arrange
    mock_db_session = AsyncMock(spec=AsyncSession)
    mock_db_session.begin.return_value = AsyncMock().__aenter__()
    async def mock_get_db_session_generator():
        yield mock_db_session

    mock_idempotency_repo = AsyncMock()
    mock_idempotency_repo.is_event_processed.return_value = False

    mock_valuation_repo = AsyncMock()
    mock_valuation_repo.get_instrument.return_value = Instrument(currency="USD")
    mock_valuation_repo.get_portfolio.return_value = Portfolio(base_currency="USD")
    mock_valuation_repo.get_fx_rate.return_value = None # Same currency
    
    snapshot_to_update = DailyPositionSnapshot(
        id=1, security_id="SEC_PRICE_01", portfolio_id="PORT_A", 
        date=date(2025,8,5), quantity=Decimal(10), cost_basis=Decimal(1000), cost_basis_local=Decimal(1000)
    )
    mock_valuation_repo.find_snapshots_to_update.return_value = [snapshot_to_update]
    mock_valuation_repo.upsert_daily_snapshot.return_value = snapshot_to_update

    with patch('services.calculators.position_valuation_calculator.app.consumers.market_price_consumer.get_async_db_session', new=mock_get_db_session_generator), \
         patch('services.calculators.position_valuation_calculator.app.consumers.market_price_consumer.IdempotencyRepository', return_value=mock_idempotency_repo), \
         patch('services.calculators.position_valuation_calculator.app.consumers.market_price_consumer.ValuationRepository', return_value=mock_valuation_repo), \
         patch('services.calculators.position_valuation_calculator.app.consumers.market_price_consumer.OutboxRepository') as mock_outbox_repo:
        
        # FIX: Ensure the instance returned by the patch is an AsyncMock
        mock_outbox_instance = AsyncMock()
        mock_outbox_repo.return_value = mock_outbox_instance

        # Act
        await consumer.process_message(mock_kafka_message)

        # Assert
        mock_idempotency_repo.is_event_processed.assert_called_once()
        mock_valuation_repo.upsert_daily_snapshot.assert_called_once()
        mock_outbox_instance.create_outbox_event.assert_called_once()
        
        call_args = mock_outbox_instance.create_outbox_event.call_args.kwargs
        assert call_args['aggregate_id'] == "PORT_A"
        
        mock_idempotency_repo.mark_event_processed.assert_called_once()
        consumer._send_to_dlq_async.assert_not_called()