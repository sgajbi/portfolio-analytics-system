# tests/unit/services/persistence_service/consumers/test_persistence_market_price_consumer.py
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import date
from decimal import Decimal
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession
from portfolio_common.events import MarketPriceEvent
from portfolio_common.logging_utils import correlation_id_var
from src.services.persistence_service.app.consumers.market_price_consumer import MarketPriceConsumer
from src.services.persistence_service.app.repositories.market_price_repository import MarketPriceRepository
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.valuation_job_repository import ValuationJobRepository

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

@pytest.fixture
def mock_dependencies():
    """A fixture to patch all external dependencies for a consumer test."""
    mock_repo = AsyncMock(spec=MarketPriceRepository)
    mock_idempotency_repo = AsyncMock(spec=IdempotencyRepository)
    mock_valuation_job_repo = AsyncMock(spec=ValuationJobRepository)

    mock_db_session = AsyncMock(spec=AsyncSession)
    mock_transaction = AsyncMock()
    # FIX: `begin` must be an awaitable mock that returns the transaction object
    mock_db_session.begin = AsyncMock(return_value=mock_transaction)

    async def get_session_gen():
        yield mock_db_session
    
    with patch(
        "src.services.persistence_service.app.consumers.market_price_consumer.get_async_db_session", new=get_session_gen
    ), patch(
        "src.services.persistence_service.app.consumers.market_price_consumer.MarketPriceRepository", return_value=mock_repo
    ), patch(
        "src.services.persistence_service.app.consumers.market_price_consumer.IdempotencyRepository", return_value=mock_idempotency_repo
    ), patch(
        "src.services.persistence_service.app.consumers.market_price_consumer.ValuationJobRepository", return_value=mock_valuation_job_repo
    ):
        yield {
            "repo": mock_repo,
            "idempotency_repo": mock_idempotency_repo,
            "valuation_job_repo": mock_valuation_job_repo,
        }

async def test_process_message_success(
    market_price_consumer: MarketPriceConsumer,
    mock_kafka_message: MagicMock,
    valid_market_price_event: MarketPriceEvent,
    mock_dependencies: dict
):
    """
    GIVEN a valid market price message
    WHEN the process_message method is called
    THEN it should save the price, find affected portfolios, and create valuation jobs.
    """
    # Arrange
    mock_repo = mock_dependencies["repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]
    mock_valuation_job_repo = mock_dependencies["valuation_job_repo"]

    mock_repo.find_portfolios_with_open_position_before_date.return_value = ["PORT_A", "PORT_B"]
    mock_idempotency_repo.is_event_processed.return_value = False
    
    token = correlation_id_var.set('test-corr-id')
    try:
        # Act
        await market_price_consumer._process_message_with_retry(mock_kafka_message)
    finally:
        correlation_id_var.reset(token)

    # Assert
    mock_repo.create_market_price.assert_called_once()
    mock_repo.find_portfolios_with_open_position_before_date.assert_called_once_with(
        security_id=valid_market_price_event.security_id,
        price_date=valid_market_price_event.price_date
    )
    
    assert mock_valuation_job_repo.upsert_job.call_count == 2
    mock_valuation_job_repo.upsert_job.assert_any_call(
        portfolio_id="PORT_A", security_id=valid_market_price_event.security_id,
        valuation_date=valid_market_price_event.price_date, correlation_id='test-corr-id'
    )
    mock_valuation_job_repo.upsert_job.assert_any_call(
        portfolio_id="PORT_B", security_id=valid_market_price_event.security_id,
        valuation_date=valid_market_price_event.price_date, correlation_id='test-corr-id'
    )

    market_price_consumer._send_to_dlq_async.assert_not_called()