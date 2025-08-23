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
    # 1. Assert that pg_insert was called with the correct table model
    mock_pg_insert.assert_called_once()
    assert mock_pg_insert.call_args[0][0].__tablename__ == 'recalculation_jobs'

    # 2. Assert that the .values() method was called with the correct data
    called_values = mock_pg_insert.return_value.values.call_args.kwargs
    assert called_values['portfolio_id'] == job_details['portfolio_id']
    assert called_values['status'] == 'PENDING'
    
    # 3. Assert that the on_conflict_do_update method was configured correctly
    on_conflict_args = mock_pg_insert.return_value.values.return_value.on_conflict_do_update.call_args
    assert on_conflict_args.kwargs['index_elements'] == ['portfolio_id', 'security_id']
    
    # 4. Verify that the LEAST function is being used to update the from_date
    update_dict = on_conflict_args.kwargs['set_']
    assert "least(recalculation_jobs.from_date" in str(update_dict['from_date'].compile())

    # 5. Assert that the final constructed statement was executed
    mock_db_session.execute.assert_awaited_once_with(mock_final_statement)