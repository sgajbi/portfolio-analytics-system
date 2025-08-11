# tests/unit/libs/portfolio-common/test_valuation_job_repository.py
import pytest
from unittest.mock import AsyncMock, patch, ANY, MagicMock
from datetime import date

from portfolio_common.valuation_job_repository import ValuationJobRepository

pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Provides a mock SQLAlchemy AsyncSession."""
    session = AsyncMock()
    session.execute = AsyncMock()
    return session

@pytest.fixture
def repository(mock_db_session: AsyncMock) -> ValuationJobRepository:
    """Provides an instance of the repository with a mock session."""
    return ValuationJobRepository(mock_db_session)

# Patch 'pg_insert' from the location where it's used in the repository code
@patch('portfolio_common.valuation_job_repository.pg_insert')
async def test_upsert_job_builds_correct_statement(mock_pg_insert, repository: ValuationJobRepository, mock_db_session: AsyncMock):
    """
    GIVEN valuation job details
    WHEN upsert_job is called
    THEN it should construct and execute an insert statement with the correct values and on_conflict_do_update clause.
    """
    # Arrange
    # The chain of calls pg_insert().values().on_conflict_do_update() returns a final object.
    # We can mock this chain to return a final mock object that we can check for execution.
    mock_final_statement = MagicMock()
    mock_pg_insert.return_value.values.return_value.on_conflict_do_update.return_value = mock_final_statement

    job_details = {
        "portfolio_id": "PORT_VJR_01",
        "security_id": "SEC_VJR_01",
        "valuation_date": date(2025, 8, 11),
        "correlation_id": "corr-vjr-123"
    }

    # Act
    await repository.upsert_job(**job_details)

    # Assert
    # 1. Assert that pg_insert was called with the correct table model
    mock_pg_insert.assert_called_once()
    assert mock_pg_insert.call_args[0][0].__tablename__ == 'portfolio_valuation_jobs'

    # 2. Assert that the .values() method was called with the correct data
    mock_pg_insert.return_value.values.assert_called_once()
    # --- THIS IS THE FIX ---
    called_values = mock_pg_insert.return_value.values.call_args.kwargs
    # --- END FIX ---
    assert called_values['portfolio_id'] == job_details['portfolio_id']
    assert called_values['security_id'] == job_details['security_id']
    assert called_values['valuation_date'] == job_details['valuation_date']
    assert called_values['status'] == 'PENDING'
    
    # 3. Assert that the on_conflict_do_update method was configured correctly
    mock_pg_insert.return_value.values.return_value.on_conflict_do_update.assert_called_once_with(
        index_elements=['portfolio_id', 'security_id', 'valuation_date'],
        set_=ANY
    )

    # 4. Assert that the final constructed statement was executed
    mock_db_session.execute.assert_awaited_once_with(mock_final_statement)