# tests/unit/services/calculators/performance_calculator_service/consumers/test_performance_consumer.py
import pytest
from unittest.mock import MagicMock, patch, AsyncMock, ANY
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from portfolio_common.events import PortfolioTimeseriesGeneratedEvent
from portfolio_common.database_models import PortfolioTimeseries
from src.services.calculators.performance_calculator_service.app.consumers.performance_consumer import PerformanceCalculatorConsumer
from src.services.calculators.performance_calculator_service.app.repositories.performance_repository import PerformanceRepository
from src.services.calculators.performance_calculator_service.app.repositories.timeseries_repository import TimeseriesRepository
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.outbox_repository import OutboxRepository

pytestmark = pytest.mark.asyncio

@pytest.fixture
def consumer() -> PerformanceCalculatorConsumer:
    consumer = PerformanceCalculatorConsumer(
        bootstrap_servers="mock", topic="mock", group_id="mock"
    )
    consumer._send_to_dlq_async = AsyncMock()
    return consumer

@pytest.fixture
def mock_event() -> PortfolioTimeseriesGeneratedEvent:
    return PortfolioTimeseriesGeneratedEvent(
        portfolio_id="PERF_CONS_TEST_01",
        date=date(2025, 8, 18)
    )

@pytest.fixture
def mock_kafka_message(mock_event: PortfolioTimeseriesGeneratedEvent) -> MagicMock:
    mock_msg = MagicMock()
    mock_msg.value.return_value = mock_event.model_dump_json().encode('utf-8')
    mock_msg.topic.return_value = "portfolio_timeseries_generated"
    mock_msg.partition.return_value = 0
    mock_msg.offset.return_value = 1
    mock_msg.headers.return_value = []
    return mock_msg

@pytest.fixture
def mock_dependencies():
    mock_idempotency_repo = AsyncMock(spec=IdempotencyRepository)
    mock_outbox_repo = AsyncMock(spec=OutboxRepository)
    mock_perf_repo = AsyncMock(spec=PerformanceRepository)
    mock_ts_repo = AsyncMock(spec=TimeseriesRepository)
    
    mock_db_session = AsyncMock(spec=AsyncSession)
    mock_db_session.begin.return_value = AsyncMock()
    
    async def get_session_gen():
        yield mock_db_session

    with patch("src.services.calculators.performance_calculator_service.app.consumers.performance_consumer.get_async_db_session", new=get_session_gen), \
         patch("src.services.calculators.performance_calculator_service.app.consumers.performance_consumer.IdempotencyRepository", return_value=mock_idempotency_repo), \
         patch("src.services.calculators.performance_calculator_service.app.consumers.performance_consumer.OutboxRepository", return_value=mock_outbox_repo), \
         patch("src.services.calculators.performance_calculator_service.app.consumers.performance_consumer.PerformanceRepository", return_value=mock_perf_repo), \
         patch("src.services.calculators.performance_calculator_service.app.consumers.performance_consumer.TimeseriesRepository", return_value=mock_ts_repo):
        yield {
            "idempotency_repo": mock_idempotency_repo, "outbox_repo": mock_outbox_repo,
            "perf_repo": mock_perf_repo, "ts_repo": mock_ts_repo
        }

async def test_process_message_success(
    consumer: PerformanceCalculatorConsumer,
    mock_kafka_message: MagicMock,
    mock_event: PortfolioTimeseriesGeneratedEvent,
    mock_dependencies: dict
):
    """
    GIVEN a valid timeseries event
    WHEN the consumer processes it
    THEN it should calculate metrics, save them, and create an outbox event.
    """
    # ARRANGE
    mock_idempotency_repo = mock_dependencies["idempotency_repo"]
    mock_outbox_repo = mock_dependencies["outbox_repo"]
    mock_perf_repo = mock_dependencies["perf_repo"]
    mock_ts_repo = mock_dependencies["ts_repo"]

    mock_idempotency_repo.is_event_processed.return_value = False
    mock_ts_repo.get_portfolio_timeseries_for_date.return_value = PortfolioTimeseries(
        eod_market_value=10200, bod_cashflow=100, eod_cashflow=-50, fees=2
    )
    mock_ts_repo.get_last_portfolio_timeseries_before.return_value = PortfolioTimeseries(
        eod_market_value=10050
    )

    # ACT
    await consumer.process_message(mock_kafka_message)

    # ASSERT
    mock_ts_repo.get_portfolio_timeseries_for_date.assert_awaited_once_with(mock_event.portfolio_id, mock_event.date)
    mock_perf_repo.upsert_daily_metrics.assert_awaited_once()
    
    # Check that both NET and GROSS metrics were saved
    saved_metrics = mock_perf_repo.upsert_daily_metrics.call_args[0][0]
    assert len(saved_metrics) == 2
    assert saved_metrics[0].return_basis == "NET"
    assert saved_metrics[1].return_basis == "GROSS"
    
    mock_outbox_repo.create_outbox_event.assert_awaited_once()
    mock_idempotency_repo.mark_event_processed.assert_awaited_once()
    consumer._send_to_dlq_async.assert_not_called()