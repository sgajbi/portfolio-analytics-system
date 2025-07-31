# services/persistence_service/tests/unit/consumers/test_market_price_consumer.py
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import date
from decimal import Decimal

from portfolio_common.kafka_consumer import correlation_id_cv
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
    consumer._producer = MagicMock()
    consumer._send_to_dlq = AsyncMock()
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
    mock_repo = MagicMock()
    correlation_id = 'corr-price-456'
    correlation_id_cv.set(correlation_id)

    with patch(
        "services.persistence_service.app.consumers.market_price_consumer.get_db_session"
    ), patch(
        "services.persistence_service.app.consumers.market_price_consumer.MarketPriceRepository", return_value=mock_repo
    ):
        # Act
        await market_price_consumer.process_message(mock_kafka_message)

        # Assert
        # 1. Verify the repository was called correctly
        mock_repo.create_market_price.assert_called_once()
        call_args = mock_repo.create_market_price.call_args[0][0]
        assert isinstance(call_args, MarketPriceEvent)
        assert call_args.security_id == valid_market_price_event.security_id

        # 2. Verify that the completion event was published
        mock_producer = market_price_consumer._producer
        mock_producer.publish_message.assert_called_once()
        
        # 3. Verify the content of the published message
        publish_args = mock_producer.publish_message.call_args.kwargs
        assert publish_args['topic'] == KAFKA_MARKET_PRICE_PERSISTED_TOPIC
        assert publish_args['key'] == valid_market_price_event.security_id
        assert publish_args['value']['price'] == str(valid_market_price_event.price) # JSON value will be a string
        assert ('X-Correlation-ID', correlation_id.encode('utf-8')) in publish_args['headers']

        # 4. Ensure the DLQ method was NOT called
        market_price_consumer._send_to_dlq.assert_not_called()