# services/persistence_service/tests/unit/consumers/test_market_price_consumer.py
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import date
from decimal import Decimal

from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.events import MarketPriceEvent
from portfolio_common.config import KAFKA_MARKET_PRICE_PERSISTED_TOPIC
from services.persistence_service.app.consumers.market_price_consumer import MarketPriceConsumer

# Mark all tests in this file as asyncio
pytestmark = pytest.mark.asyncio

@pytest.fixture
def market_price_consumer():
    """Provides an instance of the consumer for testing."""
    consumer = MarketPriceConsumer(
        bootstrap_servers="mock_server",
        topic="market_prices",
        group_id="test_group",
        dlq_topic="persistence.dlq"
    )
    consumer._send_to_dlq_async = AsyncMock()
    return consumer

@pytest.fixture
def valid_market_price_event():
    """Provides a valid MarketPriceEvent object."""
    return MarketPriceEvent(
        security_id="SEC_TEST_PRICE",
        price_date=date(2025, 7, 31),
        price=Decimal("125.50"),
        currency="USD"
    )

@pytest.fixture
def mock_kafka_message(valid_market_price_event: MarketPriceEvent):
    """Creates a mock Kafka message containing a valid market price."""
    mock_message = MagicMock()
    mock_message.value.return_value = valid_market_price_event.model_dump_json().encode('utf-8')
    mock_message.key.return_value = valid_market_price_event.security_id.encode('utf-8')
    mock_message.error.return_value = None
    mock_message.topic.return_value = "market_prices"
    mock_message.partition.return_value = 0
    mock_message.offset.return_value = 1
    mock_message.headers.return_value = [('correlation_id', b'test-corr-id')]
    return mock_message


async def test_process_message_success(
    market_price_consumer: MarketPriceConsumer,
    mock_kafka_message: MagicMock,
    valid_market_price_event: MarketPriceEvent
):
    """
    GIVEN a valid market price message
    WHEN the process_message method is called
    THEN it should call the repository to save the price
    AND publish a market_price_persisted event.
    """
    # Arrange
    mock_repo = AsyncMock()
    mock_idempotency_repo = AsyncMock()
    mock_idempotency_repo.is_event_processed.return_value = False
    mock_outbox_repo = MagicMock()

    # --- FIX: Correct async generator mocking ---
    mock_db_session = AsyncMock()
    mock_db_session.begin.return_value = AsyncMock()
    async def mock_get_db_session_generator():
        yield mock_db_session

    with patch(
        "services.persistence_service.app.consumers.market_price_consumer.get_async_db_session", new=mock_get_db_session_generator
    ), patch(
        "services.persistence_service.app.consumers.market_price_consumer.MarketPriceRepository", return_value=mock_repo
    ), patch(
        "services.persistence_service.app.consumers.market_price_consumer.IdempotencyRepository", return_value=mock_idempotency_repo
    ), patch(
        "services.persistence_service.app.consumers.market_price_consumer.OutboxRepository", return_value=mock_outbox_repo
    ):
        # Act
        await market_price_consumer._process_message_with_retry(mock_kafka_message)

        # Assert
        mock_repo.create_market_price.assert_called_once()
        call_args = mock_repo.create_market_price.call_args[0][0]
        assert isinstance(call_args, MarketPriceEvent)
        assert call_args.security_id == valid_market_price_event.security_id

        mock_outbox_repo.create_outbox_event.assert_called_once()
        market_price_consumer._send_to_dlq_async.assert_not_called()