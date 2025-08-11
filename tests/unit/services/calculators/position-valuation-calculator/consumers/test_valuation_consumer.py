# tests/unit/services/calculators/position-valuation-calculator/consumers/test_valuation_consumer.py
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import date
from decimal import Decimal

from services.calculators.position_valuation_calculator.app.consumers.valuation_consumer import ValuationConsumer
from portfolio_common.events import PortfolioValuationRequiredEvent
from portfolio_common.database_models import DailyPositionSnapshot, MarketPrice, Instrument, Portfolio
from portfolio_common.logging_utils import correlation_id_var

pytestmark = pytest.mark.asyncio

@pytest.fixture
def consumer() -> ValuationConsumer:
    """Provides a clean instance of the ValuationConsumer."""
    consumer = ValuationConsumer(
        bootstrap_servers="mock_server",
        topic="valuation_required",
        group_id="test_group",
    )
    consumer._send_to_dlq_async = AsyncMock()
    return consumer

@pytest.fixture
def mock_event() -> PortfolioValuationRequiredEvent:
    """Provides a consistent valuation event for tests."""
    return PortfolioValuationRequiredEvent(
        portfolio_id="PORT_VAL_01",
        security_id="SEC_VAL_01",
        valuation_date=date(2025, 8, 1)
    )

@pytest.fixture
def mock_kafka_message(mock_event: PortfolioValuationRequiredEvent) -> MagicMock:
    """Creates a mock Kafka message from the event."""
    mock_msg = MagicMock()
    mock_msg.value.return_value = mock_event.model_dump_json().encode('utf-8')
    mock_msg.key.return_value = mock_event.portfolio_id.encode('utf-8')
    mock_msg.topic.return_value = "valuation_required"
    mock_msg.partition.return_value = 0
    mock_msg.offset.return_value = 1
    mock_msg.error.return_value = None
    mock_msg.headers.return_value = [('correlation_id', b'test-corr-id-123')]
    return mock_msg

async def test_valuation_consumer_success(consumer: ValuationConsumer, mock_kafka_message: MagicMock, mock_event: PortfolioValuationRequiredEvent):
    """
    GIVEN a valid valuation required event
    WHEN the consumer processes the message
    THEN it should fetch all necessary data, perform valuation, and save the results.
    """
    # ARRANGE
    mock_db_session = AsyncMock()

    # FIX: Correctly mock the async context manager for `db.begin()`.
    # `begin()` itself is a regular method that returns an async context manager.
    mock_db_session.begin = MagicMock()
    mock_transaction_context = AsyncMock()
    mock_db_session.begin.return_value = mock_transaction_context
    mock_transaction_context.__aenter__.return_value = None # This is what `async with` will use.
    mock_transaction_context.__aexit__.return_value = None

    async def get_db_session_gen():
        yield mock_db_session

    mock_idempotency_repo = AsyncMock()
    mock_idempotency_repo.is_event_processed.return_value = False
    mock_outbox_repo = AsyncMock()
    mock_valuation_repo = AsyncMock()

    # FIX: Use Decimal for numeric fields in the mock data
    mock_snapshot = DailyPositionSnapshot(
        id=1,
        quantity=Decimal("100"),
        cost_basis=Decimal("10000"),
        cost_basis_local=Decimal("8000"),
        security_id='SEC_VAL_01',
        portfolio_id='PORT_VAL_01',
        date=date(2025, 8, 1)
    )
    mock_valuation_repo.get_daily_snapshot.return_value = mock_snapshot
    mock_valuation_repo.get_instrument.return_value = Instrument(currency="EUR")
    mock_valuation_repo.get_portfolio.return_value = Portfolio(base_currency="USD")
    mock_valuation_repo.get_latest_price_for_position.return_value = MarketPrice(price=Decimal("90"), currency="EUR")
    mock_valuation_repo.get_fx_rate.return_value = None
    mock_valuation_repo.upsert_daily_snapshot.return_value = mock_snapshot

    with patch(
        "services.calculators.position_valuation_calculator.app.consumers.valuation_consumer.get_async_db_session", new=get_db_session_gen
    ), patch(
        "services.calculators.position_valuation_calculator.app.consumers.valuation_consumer.IdempotencyRepository", return_value=mock_idempotency_repo
    ), patch(
        "services.calculators.position_valuation_calculator.app.consumers.valuation_consumer.ValuationRepository", return_value=mock_valuation_repo
    ), patch(
        "services.calculators.position_valuation_calculator.app.consumers.valuation_consumer.OutboxRepository", return_value=mock_outbox_repo
    ):
        token = correlation_id_var.set('test-corr-id-123')
        try:
            # ACT
            await consumer.process_message(mock_kafka_message)
        finally:
            correlation_id_var.reset(token)

        # ASSERT
        mock_idempotency_repo.is_event_processed.assert_called_once()
        mock_valuation_repo.get_daily_snapshot.assert_called_once_with(mock_event.portfolio_id, mock_event.security_id, mock_event.valuation_date)
        mock_valuation_repo.upsert_daily_snapshot.assert_called_once()
        
        mock_valuation_repo.update_job_status.assert_called_once_with(mock_event.portfolio_id, mock_event.security_id, mock_event.valuation_date, 'COMPLETE')
        
        mock_outbox_repo.create_outbox_event.assert_called_once()
        consumer._send_to_dlq_async.assert_not_called()