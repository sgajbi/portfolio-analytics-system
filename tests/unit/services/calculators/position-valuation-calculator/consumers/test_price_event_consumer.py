# tests/unit/services/calculators/position-valuation-calculator/consumers/test_price_event_consumer.py
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession
from portfolio_common.events import MarketPricePersistedEvent
from portfolio_common.recalculation_job_repository import RecalculationJobRepository
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
    mock_recalc_job_repo = AsyncMock(spec=RecalculationJobRepository)
    mock_valuation_job_repo = AsyncMock(spec=ValuationJobRepository)
    
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
        "services.calculators.position_valuation_calculator.app.consumers.price_event_consumer.RecalculationJobRepository", return_value=mock_recalc_job_repo
    ), patch(
        "services.calculators.position_valuation_calculator.app.consumers.price_event_consumer.ValuationJobRepository", return_value=mock_valuation_job_repo
    ):
        yield {
            "repo": mock_repo,
            "idempotency_repo": mock_idempotency_repo,
            "recalc_job_repo": mock_recalc_job_repo,
            "valuation_job_repo": mock_valuation_job_repo
        }

async def test_creates_recalculation_job_for_backdated_price(
    consumer: PriceEventConsumer,
    mock_kafka_message: MagicMock,
    mock_event: MarketPricePersistedEvent,
    mock_dependencies: dict
):
    """
    GIVEN a back-dated market price event
    WHEN the message is processed
    THEN it should create a RECALCULATION job for each affected portfolio.
    """
    # ARRANGE
    mock_repo = mock_dependencies["repo"]
    mock_recalc_job_repo = mock_dependencies["recalc_job_repo"]
    mock_valuation_job_repo = mock_dependencies["valuation_job_repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]

    mock_idempotency_repo.is_event_processed.return_value = False
    mock_repo.find_portfolios_holding_security_on_date.return_value = ["PORT_01"]
    # Simulate a back-dated event by setting latest business date after the price date
    mock_repo.get_latest_business_date.return_value = date(2025, 8, 10)
    
    # ACT
    await consumer.process_message(mock_kafka_message)

    # ASSERT
    mock_recalc_job_repo.upsert_job.assert_awaited_once()
    mock_valuation_job_repo.upsert_job.assert_not_called()
    call_args = mock_recalc_job_repo.upsert_job.call_args.kwargs
    assert call_args['from_date'] == mock_event.price_date

async def test_creates_valuation_job_for_current_price(
    consumer: PriceEventConsumer,
    mock_kafka_message: MagicMock,
    mock_event: MarketPricePersistedEvent,
    mock_dependencies: dict
):
    """
    GIVEN a current-day market price event
    WHEN the message is processed
    THEN it should create a VALUATION job for each affected portfolio.
    """
    # ARRANGE
    mock_repo = mock_dependencies["repo"]
    mock_recalc_job_repo = mock_dependencies["recalc_job_repo"]
    mock_valuation_job_repo = mock_dependencies["valuation_job_repo"]
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]

    mock_idempotency_repo.is_event_processed.return_value = False
    mock_repo.find_portfolios_holding_security_on_date.return_value = ["PORT_01"]
    # Simulate a current event by setting latest business date equal to the price date
    mock_repo.get_latest_business_date.return_value = mock_event.price_date
    
    # ACT
    await consumer.process_message(mock_kafka_message)

    # ASSERT
    mock_valuation_job_repo.upsert_job.assert_awaited_once()
    mock_recalc_job_repo.upsert_job.assert_not_called()
    call_args = mock_valuation_job_repo.upsert_job.call_args.kwargs
    assert call_args['valuation_date'] == mock_event.price_date