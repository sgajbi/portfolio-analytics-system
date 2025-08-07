# services/calculators/position-valuation-calculator/tests/unit/consumers/test_market_price_consumer.py
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session
from consumers.market_price_consumer import MarketPriceConsumer
from portfolio_common.events import MarketPriceEvent
from portfolio_common.database_models import DailyPositionSnapshot

pytestmark = pytest.mark.asyncio

@pytest.fixture
def consumer():
    """Provides a clean instance of the MarketPriceConsumer."""
    c = MarketPriceConsumer(
        bootstrap_servers="mock_server",
        topic="market_price_persisted",
        group_id="test_group",
        dlq_topic="test.dlq"
    )
    c._producer = MagicMock()
    c._send_to_dlq = AsyncMock()
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
    return mock_msg

async def test_process_message_success(consumer: MarketPriceConsumer, mock_kafka_message: MagicMock, mock_event: MarketPriceEvent):
    """
    GIVEN a new market price event for a security held in two portfolios
    WHEN the consumer processes the message
    THEN it should update snapshots for both portfolios and publish two completion events.
    """
    # Arrange
    mock_db_session = MagicMock(spec=Session)
    mock_transaction_context = MagicMock()
    mock_transaction_context.__enter__.return_value = None
    mock_transaction_context.__exit__.return_value = (None, None, None)
    mock_db_session.begin.return_value = mock_transaction_context

    mock_idempotency_repo = MagicMock()
    mock_idempotency_repo.is_event_processed.return_value = False

    # SIMPLIFIED: Mock the single high-level repository method
    mock_valuation_repo = MagicMock()
    updated_snapshots = [
        DailyPositionSnapshot(id=1, security_id="SEC_PRICE_01", portfolio_id="PORT_A", date=date(2025,8,5)),
        DailyPositionSnapshot(id=2, security_id="SEC_PRICE_01", portfolio_id="PORT_B", date=date(2025,8,5))
    ]
    mock_valuation_repo.update_snapshots_for_market_price.return_value = updated_snapshots
    
    with patch('app.consumers.market_price_consumer.get_db_session', return_value=iter([mock_db_session])), \
         patch('app.consumers.market_price_consumer.IdempotencyRepository', return_value=mock_idempotency_repo), \
         patch('app.consumers.market_price_consumer.ValuationRepository', return_value=mock_valuation_repo):
        
        # Act
        await consumer.process_message(mock_kafka_message)

        # Assert
        mock_idempotency_repo.is_event_processed.assert_called_once()
        # Assert that our new high-level method was called
        mock_valuation_repo.update_snapshots_for_market_price.assert_called_once_with(mock_event)
        mock_idempotency_repo.mark_event_processed.assert_called_once()
        # Should publish one event per returned snapshot
        assert consumer._producer.publish_message.call_count == 2
        consumer._send_to_dlq.assert_not_called()

async def test_process_message_skips_processed_event(consumer: MarketPriceConsumer, mock_kafka_message: MagicMock):
    """
    GIVEN a market price event that has already been processed
    WHEN the consumer processes the message
    THEN it should skip all business logic.
    """
    # Arrange
    mock_db_session = MagicMock(spec=Session)
    mock_transaction_context = MagicMock()
    mock_transaction_context.__enter__.return_value = None
    mock_transaction_context.__exit__.return_value = (None, None, None)
    mock_db_session.begin.return_value = mock_transaction_context

    mock_idempotency_repo = MagicMock()
    mock_idempotency_repo.is_event_processed.return_value = True # DUPLICATE

    mock_valuation_repo = MagicMock()
    
    with patch('app.consumers.market_price_consumer.get_db_session', return_value=iter([mock_db_session])), \
         patch('app.consumers.market_price_consumer.IdempotencyRepository', return_value=mock_idempotency_repo), \
         patch('app.consumers.market_price_consumer.ValuationRepository', return_value=mock_valuation_repo):

        # Act
        await consumer.process_message(mock_kafka_message)

        # Assert
        mock_idempotency_repo.is_event_processed.assert_called_once()
        mock_valuation_repo.update_snapshots_for_market_price.assert_not_called()
        mock_idempotency_repo.mark_event_processed.assert_not_called()
        consumer._producer.publish_message.assert_not_called()
        consumer._send_to_dlq.assert_not_called()