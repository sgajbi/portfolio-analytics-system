# tests/unit/libs/portfolio-common/test_recalculation_job_repository.py
import pytest
from unittest.mock import AsyncMock, patch, ANY, MagicMock
from datetime import date

from portfolio_common.recalculation_job_repository import RecalculationJobRepository

pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Provides a mock SQLAlchemy AsyncSession."""
    session = AsyncMock()
    session.execute = AsyncMock()
    return session

@pytest.fixture
def repository(mock_db_session: AsyncMock) -> RecalculationJobRepository:
    """Provides an instance of the repository with a mock session."""
    return RecalculationJobRepository(mock_db_session)

@patch('portfolio_common.recalculation_job_repository.pg_insert')
async def test_upsert_job_builds_correct_statement(mock_pg_insert, repository: RecalculationJobRepository, mock_db_session: AsyncMock):
    """
    GIVEN recalculation job details
    WHEN upsert_job is called
    THEN it should construct an insert statement with the correct values and on_conflict_do_update clause,
    including the LEAST function to ensure the earliest date is used.
    """
    # ARRANGE
    mock_final_statement = MagicMock()
    mock_pg_insert.return_value.values.return_value.on_conflict_do_update.return_value = mock_final_statement

    job_details = {
        "portfolio_id": "PORT_RECALC_01",
        "security_id": "SEC_RECALC_01",
        "from_date": date(2025, 8, 1),
        "correlation_id": "corr-recalc-123"
    }

    # ACT
    await repository.upsert_job(**job_details)

    # ASSERT
    mock_pg_insert.assert_called_once()
    assert mock_pg_insert.call_args[0][0].__tablename__ == 'recalculation_jobs'
    called_values = mock_pg_insert.return_value.values.call_args.kwargs
    assert called_values['portfolio_id'] == job_details['portfolio_id']
    assert called_values['status'] == 'PENDING'
    on_conflict_args = mock_pg_insert.return_value.values.return_value.on_conflict_do_update.call_args
    assert on_conflict_args.kwargs['index_elements'] == ['portfolio_id', 'security_id']
    update_dict = on_conflict_args.kwargs['set_']
    assert "least(recalculation_jobs.from_date" in str(update_dict['from_date'].compile())
    mock_db_session.execute.assert_awaited_once_with(mock_final_statement)

async def test_is_job_processing(repository: RecalculationJobRepository, mock_db_session: AsyncMock):
    """
    GIVEN a portfolio and security ID
    WHEN is_job_processing is called
    THEN it should construct and execute the correct SELECT EXISTS query.
    """
    # ARRANGE
    mock_result = MagicMock()
    mock_result.scalar.return_value = True
    mock_db_session.execute.return_value = mock_result

    # ACT
    result = await repository.is_job_processing("P1", "S1")

    # ASSERT
    assert result is True
    mock_db_session.execute.assert_awaited_once()
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    
    assert "SELECT EXISTS" in compiled_query
    assert "recalculation_jobs.portfolio_id = 'P1'" in compiled_query
    assert "recalculation_jobs.security_id = 'S1'" in compiled_query
    assert "recalculation_jobs.status = 'PROCESSING'" in compiled_query