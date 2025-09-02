# tests/unit/services/query_service/services/test_position_service.py
import pytest
from unittest.mock import AsyncMock, patch
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from src.services.query_service.app.services.position_service import PositionService
from src.services.query_service.app.repositories.position_repository import PositionRepository
from portfolio_common.database_models import PositionHistory, DailyPositionSnapshot, Instrument, PositionState

pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_position_repo() -> AsyncMock:
    """Provides a mock PositionRepository."""
    repo = AsyncMock(spec=PositionRepository)
    
    mock_history_obj = PositionHistory(transaction_id="T1", position_date=date(2025,1,1), quantity=1, cost_basis=1, cost_basis_local=1)
    repo.get_position_history_by_security.return_value = [(mock_history_obj, "CURRENT")]
    
    # --- FIX: Return the correct 3-tuple structure ---
    mock_snapshot = DailyPositionSnapshot(
        security_id="S1", 
        quantity=Decimal(100), cost_basis=Decimal(1000), 
        date=date(2025, 1, 1)
    )
    mock_instrument = Instrument(
        name="Test Instrument", isin="ISIN123", currency="USD", 
        asset_class="Equity", sector="Technology", country_of_risk="US"
    )
    mock_state = PositionState(status="CURRENT")

    repo.get_latest_positions_by_portfolio.return_value = [
        (mock_snapshot, mock_instrument, mock_state)
    ]
    # --- END FIX ---
    return repo

async def test_get_position_history(mock_position_repo: AsyncMock):
    """Tests the position history service method."""
    # ARRANGE
    with patch(
        "src.services.query_service.app.services.position_service.PositionRepository",
        return_value=mock_position_repo
    ):
        service = PositionService(AsyncMock())
        params = {"portfolio_id": "P1", "security_id": "S1", "start_date": date(2025, 1, 1), "end_date": date(2025, 1, 31)}

        # ACT
        response = await service.get_position_history(**params)

        # ASSERT
        mock_position_repo.get_position_history_by_security.assert_awaited_once_with(**params)
        assert len(response.positions) == 1
        assert response.positions[0].transaction_id == "T1"
        assert response.positions[0].valuation is None 
        assert response.positions[0].reprocessing_status == "CURRENT"

async def test_get_latest_positions(mock_position_repo: AsyncMock):
    """Tests the latest portfolio positions service method."""
    # ARRANGE
    with patch(
        "src.services.query_service.app.services.position_service.PositionRepository",
        return_value=mock_position_repo
    ):
        service = PositionService(AsyncMock())

        # ACT
        response = await service.get_portfolio_positions(portfolio_id="P1")

        # ASSERT
        mock_position_repo.get_latest_positions_by_portfolio.assert_awaited_once_with("P1")
        assert len(response.positions) == 1
        assert response.positions[0].security_id == "S1"
        assert response.positions[0].instrument_name == "Test Instrument"
        assert response.positions[0].reprocessing_status == "CURRENT"
        assert response.positions[0].asset_class == "Equity"