from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.services.operations_service import OperationsService

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_ops_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(mock_ops_repo: AsyncMock) -> OperationsService:
    with patch(
        "src.services.query_service.app.services.operations_service.OperationsRepository",
        return_value=mock_ops_repo,
    ):
        return OperationsService(AsyncMock(spec=AsyncSession))


async def test_get_support_overview(service: OperationsService, mock_ops_repo: AsyncMock):
    mock_ops_repo.get_current_portfolio_epoch.return_value = 2
    mock_ops_repo.get_active_reprocessing_keys_count.return_value = 1
    mock_ops_repo.get_pending_valuation_jobs_count.return_value = 4
    mock_ops_repo.get_pending_aggregation_jobs_count.return_value = 1
    mock_ops_repo.get_latest_transaction_date.return_value = date(2025, 8, 31)
    mock_ops_repo.get_latest_snapshot_date_for_current_epoch.return_value = date(2025, 8, 30)

    response = await service.get_support_overview("P1")

    assert response.portfolio_id == "P1"
    assert response.current_epoch == 2
    assert response.active_reprocessing_keys == 1
    assert response.pending_valuation_jobs == 4
    assert response.pending_aggregation_jobs == 1
    assert response.latest_transaction_date == date(2025, 8, 31)
    assert response.latest_position_snapshot_date == date(2025, 8, 30)


async def test_get_lineage_raises_when_state_missing(
    service: OperationsService, mock_ops_repo: AsyncMock
):
    mock_ops_repo.get_position_state.return_value = None

    with pytest.raises(ValueError, match="Lineage state not found"):
        await service.get_lineage("P1", "S1")


async def test_get_lineage_success(service: OperationsService, mock_ops_repo: AsyncMock):
    mock_ops_repo.get_position_state.return_value = type(
        "PositionStateStub",
        (),
        {"epoch": 3, "watermark_date": date(2025, 8, 1), "status": "CURRENT"},
    )()
    mock_ops_repo.get_latest_position_history_date.return_value = date(2025, 8, 31)
    mock_ops_repo.get_latest_daily_snapshot_date.return_value = date(2025, 8, 31)
    mock_ops_repo.get_latest_valuation_job.return_value = type(
        "ValuationJobStub",
        (),
        {"valuation_date": date(2025, 8, 31), "status": "DONE"},
    )()

    response = await service.get_lineage("P1", "S1")

    assert response.portfolio_id == "P1"
    assert response.security_id == "S1"
    assert response.epoch == 3
    assert response.latest_position_history_date == date(2025, 8, 31)
    assert response.latest_daily_snapshot_date == date(2025, 8, 31)
    assert response.latest_valuation_job_status == "DONE"
