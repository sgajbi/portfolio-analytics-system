# tests/unit/services/calculators/position-valuation-calculator/consumers/test_price_event_consumer.py
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from portfolio_common.events import MarketPricePersistedEvent
from portfolio_common.position_state_repository import PositionStateRepository
from services.calculators.position_valuation_calculator.app.consumers.price_event_consumer import PriceEventConsumer
from services.calculators.position_valuation_calculator.app.repositories.valuation_repository import ValuationRepository
from portfolio_common.idempotency_repository import IdempotencyRepository

pytestmark = pytest.mark.asyncio

@pytest.fixture
def consumer() -> PriceEventConsumer:
    """Provides a clean instance of the PriceEventConsumer."""
    consumer = PriceEventConsumer(
        bootstrap_servers="mock_server",
        topic="market_price_persisted",
        group_id="test_group",
    )
    consumer._send_to_dlq_async = AsyncMock()
    return consumer

@pytest.fixture
def mock_event() -> MarketPricePersistedEvent:
    """Provides a consistent market price event for tests."""
    return MarketPricePersistedEvent(
        security_id="SEC_TEST_PRICE_EVENT",
        price_date=date(2025, 8, 5),
        price=150.0,
        currency="USD"
    )

@pytest.fixture
def mock_kafka_message(mock_event: MarketPricePersistedEvent) -> MagicMock:
    """Creates a mock Kafka message from the event."""
    mock_msg = MagicMock()
    mock_msg.value.return_value = mock_event.model_dump_json().encode('utf-8')
    mock_msg.key.return_value = mock_event.security_id.encode('utf-8')
    mock_msg.topic.return_value = "market_price_persisted"
    mock_msg.partition.return_value = 0
    mock_msg.offset.return_value = 1
    mock_msg.headers.return_value = []
    return mock_msg

@pytest.fixture
def mock_dependencies():
    """A fixture to patch all external dependencies for the consumer test."""
    mock_repo = AsyncMock(spec=ValuationRepository)
    mock_idempotency_repo = AsyncMock(spec=IdempotencyRepository)
    mock_position_state_repo = AsyncMock(spec=PositionStateRepository)
    
    mock_db_session = AsyncMock(spec=AsyncSession)
    mock_transaction = AsyncMock()
    mock_db_session.begin.return_value = mock_transaction
    
    async def get_session_gen():
        yield mock_db_session

    with patch(
        "services.calculators.position_valuation_calculator.app.consumers.price_event_consumer.get_async_db_session", new=get_session_gen
    ), patch(
        "services.calculators.position_valuation_calculator.app.consumers.price_event_consumer.ValuationRepository", return_value=mock_repo
    ), patch(
        "services.calculators.position_valuation_calculator.app.consumers.price_event_consumer.IdempotencyRepository", return_value=mock_idempotency_repo
    ), patch(
        "services.calculators.position_valuation_calculator.app.consumers.price_event_consumer.PositionStateRepository", return_value=mock_position_state_repo
    ):
        yield {
            "repo": mock_repo,
            "idempotency_repo": mock_idempotency_repo,
            "position_state_repo": mock_position_state_repo
        }

async def test_backdated_price_resets_watermark(
    consumer: PriceEventConsumer,
    mock_kafka_message: MagicMock,
    mock_event: MarketPricePersistedEvent,
    mock_dependencies: dict
):
    """
    GIVEN a back-dated market price event
    WHEN the message is processed
    THEN it should reset the watermark for each affected portfolio.
    """
    # ARRANGE
    mock_repo = mock_dependencies["repo"]
    mock_position_state_repo = mock_dependencies["position_state_repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]

    mock_idempotency_repo.is_event_processed.return_value = False
    mock_repo.find_portfolios_holding_security_on_date.return_value = ["PORT_01", "PORT_02"]
    # Simulate a back-dated event by setting latest business date AFTER the price date
    mock_repo.get_latest_business_date.return_value = mock_event.price_date + timedelta(days=5)
    
    # ACT
    await consumer.process_message(mock_kafka_message)

    # ASSERT
    mock_position_state_repo.update_watermarks_if_older.assert_awaited_once()
    call_args = mock_position_state_repo.update_watermarks_if_older.call_args.kwargs
    
    expected_keys = [("PORT_01", mock_event.security_id), ("PORT_02", mock_event.security_id)]
    assert call_args['keys'] == expected_keys
    assert call_args['new_watermark_date'] == mock_event.price_date - timedelta(days=1)

async def test_current_price_does_not_reset_watermark(
    consumer: PriceEventConsumer,
    mock_kafka_message: MagicMock,
    mock_event: MarketPricePersistedEvent,
    mock_dependencies: dict
):
    """
    GIVEN a current-day market price event
    WHEN the message is processed
    THEN it should NOT attempt to reset any watermarks.
    """
    # ARRANGE
    mock_repo = mock_dependencies["repo"]
    mock_position_state_repo = mock_dependencies["position_state_repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]

    mock_idempotency_repo.is_event_processed.return_value = False
    # Simulate a current event
    mock_repo.get_latest_business_date.return_value = mock_event.price_date
    
    # ACT
    await consumer.process_message(mock_kafka_message)

    # ASSERT
    mock_position_state_repo.update_watermarks_if_older.assert_not_called()
    mock_repo.find_portfolios_holding_security_on_date.assert_not_called()