# tests/unit/services/query_service/services/test_instrument_service.py
import pytest
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import AsyncSession
from src.services.query_service.app.services.instrument_service import InstrumentService
from src.services.query_service.app.repositories.instrument_repository import InstrumentRepository
from portfolio_common.database_models import Instrument

pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_instrument_repo() -> AsyncMock:
    """Provides a mock InstrumentRepository."""
    repo = AsyncMock(spec=InstrumentRepository)
    
    # Mock the data returned by the repository
    repo.get_instruments.return_value = [
        Instrument(
            security_id="SEC1", name="Test Instrument 1", isin="ISIN1", 
            currency="USD", product_type="Equity"
        ),
        Instrument(
            security_id="SEC2", name="Test Instrument 2", isin="ISIN2", 
            currency="SGD", product_type="Bond"
        ),
    ]
    repo.get_instruments_count.return_value = 50 # Total count for pagination
    
    return repo

async def test_get_instruments(mock_instrument_repo: AsyncMock):
    """
    GIVEN pagination and filter parameters
    WHEN the instrument service's get_instruments method is called
    THEN it should call the repository with the correct parameters
    AND correctly map the results to the paginated response DTO.
    """
    # ARRANGE
    with patch(
        "src.services.query_service.app.services.instrument_service.InstrumentRepository",
        return_value=mock_instrument_repo
    ):
        mock_db_session = AsyncMock()
        service = InstrumentService(mock_db_session)
        
        params = {
            "skip": 10,
            "limit": 20,
            "security_id": "SEC1",
            "product_type": "Equity"
        }

        # ACT
        response_dto = await service.get_instruments(**params)

        # ASSERT
        # 1. Assert the repository methods were called correctly
        mock_instrument_repo.get_instruments_count.assert_awaited_once_with(
            security_id=params["security_id"], product_type=params["product_type"]
        )
        mock_instrument_repo.get_instruments.assert_awaited_once_with(**params)

        # 2. Assert the paginated response DTO is correct
        assert response_dto.total == 50
        assert response_dto.skip == 10
        assert response_dto.limit == 20
        assert len(response_dto.instruments) == 2
        
        # 3. Assert the mapping from DB model to DTO is correct
        assert response_dto.instruments[0].security_id == "SEC1"
        assert response_dto.instruments[1].product_type == "Bond"