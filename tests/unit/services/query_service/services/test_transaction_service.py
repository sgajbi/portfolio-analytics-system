# tests/unit/services/query_service/services/test_transaction_service.py
import pytest
from unittest.mock import AsyncMock, patch
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from src.services.query_service.app.services.transaction_service import TransactionService
from src.services.query_service.app.repositories.transaction_repository import TransactionRepository
from portfolio_common.database_models import Transaction

pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_transaction_repo() -> AsyncMock:
    """Provides a mock TransactionRepository."""
    repo = AsyncMock(spec=TransactionRepository)
    # FIX: Provide full, valid data for the mock objects
    repo.get_transactions.return_value = [
        Transaction(
            transaction_id="T1", transaction_date=datetime(2025,1,10), transaction_type="BUY",
            instrument_id="I1", security_id="S1", quantity=Decimal(10), price=Decimal(100),
            gross_transaction_amount=Decimal(1000), currency="USD"
        ), 
        Transaction(
            transaction_id="T2", transaction_date=datetime(2025,1,11), transaction_type="SELL",
            instrument_id="I2", security_id="S2", quantity=Decimal(20), price=Decimal(200),
            gross_transaction_amount=Decimal(4000), currency="USD"
        )
    ]
    repo.get_transactions_count.return_value = 25
    return repo

async def test_get_transactions(mock_transaction_repo: AsyncMock):
    """
    GIVEN filters and pagination
    WHEN the transaction service is called
    THEN it should call the repository correctly and map the results to the response DTO.
    """
    # ARRANGE
    with patch(
        "src.services.query_service.app.services.transaction_service.TransactionRepository",
        return_value=mock_transaction_repo
    ):
        service = TransactionService(AsyncMock(spec=AsyncSession))
        params = {
            "portfolio_id": "P1", "skip": 5, "limit": 10, "sort_by": "price", "sort_order": "asc",
            "security_id": "S1", "start_date": date(2025, 1, 1), "end_date": date(2025, 1, 31)
        }

        # ACT
        response_dto = await service.get_transactions(**params)

        # ASSERT
        mock_transaction_repo.get_transactions_count.assert_awaited_once_with(
            portfolio_id=params["portfolio_id"], security_id=params["security_id"],
            start_date=params["start_date"], end_date=params["end_date"]
        )
        mock_transaction_repo.get_transactions.assert_awaited_once_with(**params)
        
        assert response_dto.total == 25
        assert response_dto.skip == 5
        assert response_dto.limit == 10
        assert len(response_dto.transactions) == 2
        assert response_dto.transactions[0].transaction_id == "T1"