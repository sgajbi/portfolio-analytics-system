# tests/unit/services/recalculation_service/repositories/test_recalculation_repository.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import date
from sqlalchemy import text
from sqlalchemy.sql.expression import delete, select, update, Select, Update, Delete, TextClause

from portfolio_common.database_models import RecalculationJob
from src.services.recalculation_service.app.repositories.recalculation_repository import RecalculationRepository

pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Provides a mock SQLAlchemy AsyncSession."""
    session = AsyncMock()
    mock_result = MagicMock()
    
    mock_row_dict = {"id": 1, "portfolio_id": "P1", "security_id": "S1", "from_date": date(2025, 1, 1)}
    
    mock_result.mappings.return_value.first.return_value = mock_row_dict
    session.execute.return_value = mock_result
    return session

@pytest.fixture
def repository(mock_db_session: AsyncMock) -> RecalculationRepository:
    """Provides an instance of the repository with a mock session."""
    return RecalculationRepository(mock_db_session)


async def test_find_and_claim_job(repository: RecalculationRepository, mock_db_session: AsyncMock):
    """
    GIVEN a call to find_and_claim_job
    WHEN a job is available
    THEN it should execute the correct raw SQL for atomic locking and return a RecalculationJob instance.
    """
    # ACT
    job = await repository.find_and_claim_job()

    # ASSERT
    assert job is not None
    assert isinstance(job, RecalculationJob)
    assert job.id == 1

    mock_db_session.execute.assert_awaited_once()
    executed_stmt = mock_db_session.execute.call_args[0][0]
    # FIX: Check against the correct imported class 'TextClause'
    assert isinstance(executed_stmt, TextClause)
    assert "UPDATE recalculation_jobs" in str(executed_stmt)
    assert "FOR UPDATE SKIP LOCKED" in str(executed_stmt)
    assert "RETURNING *" in str(executed_stmt)

async def test_update_job_status(repository: RecalculationRepository, mock_db_session: AsyncMock):
    """
    GIVEN a job ID and a new status
    WHEN update_job_status is called
    THEN it should construct and execute the correct UPDATE statement.
    """
    # ACT
    await repository.update_job_status(job_id=123, status="COMPLETE")

    # ASSERT
    mock_db_session.execute.assert_awaited_once()
    executed_stmt = mock_db_session.execute.call_args[0][0]

    assert isinstance(executed_stmt, Update)
    # FIX: Inspect the .values attribute on the statement object, not the compiled object.
    assert executed_stmt.values['status'] == 'COMPLETE'
    
    compiled = executed_stmt.compile(compile_kwargs={"literal_binds": True})
    assert "recalculation_jobs.id = 123" in str(compiled.where)


async def test_delete_downstream_data(repository: RecalculationRepository, mock_db_session: AsyncMock):
    """
    GIVEN a portfolio, security, and date
    WHEN delete_downstream_data is called
    THEN it should execute DELETE statements for all four downstream tables.
    """
    # ACT
    await repository.delete_downstream_data("P1", "S1", date(2025, 1, 1))

    # ASSERT
    assert mock_db_session.execute.call_count == 4
    
    executed_stmts = [call[0][0] for call in mock_db_session.execute.call_args_list]
    table_names = {stmt.table.name for stmt in executed_stmts if isinstance(stmt, Delete)}
    
    expected_tables = {
        "portfolio_timeseries",
        "position_timeseries",
        "daily_position_snapshots",
        "position_history"
    }
    assert table_names == expected_tables

async def test_get_all_transactions_for_security(repository: RecalculationRepository, mock_db_session: AsyncMock):
    """
    GIVEN a portfolio and security
    WHEN get_all_transactions_for_security is called
    THEN it should construct a correctly filtered and ordered SELECT statement.
    """
    # ACT
    await repository.get_all_transactions_for_security("P1", "S1")

    # ASSERT
    mock_db_session.execute.assert_awaited_once()
    executed_stmt = mock_db_session.execute.call_args[0][0]

    assert isinstance(executed_stmt, Select)
    compiled = executed_stmt.compile(compile_kwargs={"literal_binds": True})
    assert "WHERE transactions.portfolio_id = 'P1' AND transactions.security_id = 'S1'" in str(compiled)
    assert "ORDER BY transactions.transaction_date ASC, transactions.id ASC" in str(compiled)