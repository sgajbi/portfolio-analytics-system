# tests/unit/libs/portfolio-common/test_recalculation_job_repository.py
import pytest
from unittest.mock import AsyncMock, patch, ANY, MagicMock
from datetime import date

from portfolio_common.recalculation_job_repository import RecalculationJobRepository
from portfolio_common.database_models import RecalculationJob

pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Provides a mock SQLAlchemy AsyncSession."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.add = MagicMock()
    return session

@pytest.fixture
def repository(mock_db_session: AsyncMock) -> RecalculationJobRepository:
    """Provides an instance of the repository with a mock session."""
    return RecalculationJobRepository(mock_db_session)


async def test_create_job_adds_to_session(repository: RecalculationJobRepository, mock_db_session: AsyncMock):
    """
    GIVEN recalculation job details
    WHEN create_job is called
    THEN it should add a correctly formed RecalculationJob object to the session and flush.
    """
    # ARRANGE
    job_details = {
        "portfolio_id": "PORT_RECALC_01",
        "security_id": "SEC_RECALC_01",
        "from_date": date(2025, 8, 1),
        "correlation_id": "corr-recalc-123"
    }

    # ACT
    await repository.create_job(**job_details)

    # ASSERT
    mock_db_session.add.assert_called_once()
    mock_db_session.flush.assert_awaited_once()

    added_object = mock_db_session.add.call_args[0][0]
    assert isinstance(added_object, RecalculationJob)
    assert added_object.portfolio_id == job_details['portfolio_id']
    assert added_object.security_id == job_details['security_id']
    assert added_object.from_date == job_details['from_date']
    assert added_object.status == 'PENDING'
    assert added_object.correlation_id == job_details['correlation_id']


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