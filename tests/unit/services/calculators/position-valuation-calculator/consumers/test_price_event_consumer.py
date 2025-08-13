# tests/unit/services/calculators/position-valuation-calculator/consumers/test_price_event_consumer.py
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from portfolio_common.events import MarketPricePersistedEvent
from portfolio_common.valuation_job_repository import ValuationJobRepository
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
    mock_job_repo = AsyncMock(spec=ValuationJobRepository)
    
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
        "services.calculators.position_valuation_calculator.app.consumers.price_event_consumer.ValuationJobRepository", return_value=mock_job_repo
    ):
        yield {
            "repo": mock_repo,
            "idempotency_repo": mock_idempotency_repo,
            "job_repo": mock_job_repo
        }

async def test_creates_jobs_for_correct_date_range(
    consumer: PriceEventConsumer,
    mock_kafka_message: MagicMock,
    mock_event: MarketPricePersistedEvent,
    mock_dependencies: dict
):
    """
    GIVEN a back-dated market price event
    WHEN the message is processed
    THEN it should create valuation jobs for each day from the price date up to the next known price date.
    """
    # ARRANGE
    mock_repo = mock_dependencies["repo"]
    mock_job_repo = mock_dependencies["job_repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]

    mock_idempotency_repo.is_event_processed.return_value = False
    mock_repo.find_portfolios_holding_security_on_date.return_value = ["PORT_01"]
    
    # Simulate the position starting before the new price, and a next price existing 3 days later
    mock_repo.get_first_transaction_date.return_value = date(2025, 8, 1)
    mock_repo.get_next_price_date.return_value = date(2025, 8, 8)

    # ACT
    await consumer.process_message(mock_kafka_message)

    # ASSERT
    # It should create jobs for 8/5, 8/6, and 8/7 (3 jobs)
    assert mock_job_repo.upsert_job.call_count == 3
    
    # Check the dates of the created jobs
    call_dates = {call.kwargs['valuation_date'] for call in mock_job_repo.upsert_job.call_args_list}
    expected_dates = {date(2025, 8, 5), date(2025, 8, 6), date(2025, 8, 7)}
    assert call_dates == expected_dates

    mock_idempotency_repo.mark_event_processed.assert_called_once()