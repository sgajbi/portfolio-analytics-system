from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.repositories.operations_repository import (
    OperationsRepository,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_db_session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def repository(mock_db_session: AsyncMock) -> OperationsRepository:
    return OperationsRepository(mock_db_session)


def mock_execute_scalar_one_or_none(mock_db_session: AsyncMock, value):
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = value
    mock_db_session.execute = AsyncMock(return_value=mock_result)


def mock_execute_scalar_one(mock_db_session: AsyncMock, value):
    mock_result = MagicMock()
    mock_result.scalar_one.return_value = value
    mock_db_session.execute = AsyncMock(return_value=mock_result)


async def test_get_current_portfolio_epoch(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_execute_scalar_one_or_none(mock_db_session, 3)

    value = await repository.get_current_portfolio_epoch("P1")

    assert value == 3
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "max(position_state.epoch)" in compiled.lower()
    assert "position_state.portfolio_id = 'P1'" in compiled


async def test_get_active_reprocessing_keys_count(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_execute_scalar_one(mock_db_session, 2)

    value = await repository.get_active_reprocessing_keys_count("P1")

    assert value == 2
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from position_state" in compiled.lower()
    assert "position_state.status = 'REPROCESSING'" in compiled


async def test_get_pending_valuation_jobs_count(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_execute_scalar_one(mock_db_session, 4)

    value = await repository.get_pending_valuation_jobs_count("P1")

    assert value == 4
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from portfolio_valuation_jobs" in compiled.lower()
    assert "portfolio_valuation_jobs.status IN ('PENDING', 'PROCESSING')" in compiled


async def test_get_pending_aggregation_jobs_count(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_execute_scalar_one(mock_db_session, 1)

    value = await repository.get_pending_aggregation_jobs_count("P1")

    assert value == 1
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from portfolio_aggregation_jobs" in compiled.lower()
    assert "portfolio_aggregation_jobs.status IN ('PENDING', 'PROCESSING')" in compiled


async def test_get_latest_transaction_date(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_execute_scalar_one_or_none(mock_db_session, date(2025, 8, 31))

    value = await repository.get_latest_transaction_date("P1")

    assert value == date(2025, 8, 31)
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "max(date(transactions.transaction_date))" in compiled.lower()
    assert "transactions.portfolio_id = 'P1'" in compiled


async def test_get_latest_snapshot_date_for_current_epoch(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_execute_scalar_one_or_none(mock_db_session, date(2025, 8, 30))

    value = await repository.get_latest_snapshot_date_for_current_epoch("P1")

    assert value == date(2025, 8, 30)
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from daily_position_snapshots" in compiled.lower()
    assert "join position_state on" in compiled.lower()
    assert "daily_position_snapshots.epoch = position_state.epoch" in compiled


async def test_get_position_state(repository: OperationsRepository, mock_db_session: AsyncMock):
    mock_state = object()
    mock_execute_scalar_one_or_none(mock_db_session, mock_state)

    value = await repository.get_position_state("P1", "S1")

    assert value is mock_state
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from position_state" in compiled.lower()
    assert "position_state.security_id = 'S1'" in compiled


async def test_get_latest_position_history_date(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_execute_scalar_one_or_none(mock_db_session, date(2025, 8, 20))

    value = await repository.get_latest_position_history_date("P1", "S1", 2)

    assert value == date(2025, 8, 20)
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "max(position_history.position_date)" in compiled.lower()
    assert "position_history.epoch = 2" in compiled


async def test_get_latest_daily_snapshot_date(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_execute_scalar_one_or_none(mock_db_session, date(2025, 8, 22))

    value = await repository.get_latest_daily_snapshot_date("P1", "S1", 2)

    assert value == date(2025, 8, 22)
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "max(daily_position_snapshots.date)" in compiled.lower()
    assert "daily_position_snapshots.epoch = 2" in compiled


async def test_get_latest_valuation_job(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_job = object()
    mock_execute_scalar_one_or_none(mock_db_session, mock_job)

    value = await repository.get_latest_valuation_job("P1", "S1", 2)

    assert value is mock_job
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from portfolio_valuation_jobs" in compiled.lower()
    assert "portfolio_valuation_jobs.epoch = 2" in compiled
    assert (
        "ORDER BY portfolio_valuation_jobs.valuation_date DESC, portfolio_valuation_jobs.id DESC"
        in compiled
    )
