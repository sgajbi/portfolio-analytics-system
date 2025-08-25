# tests/unit/services/calculators/position_calculator/core/test_position_logic.py
import pytest
from unittest.mock import AsyncMock
from datetime import date, datetime, timedelta
from decimal import Decimal

from portfolio_common.events import TransactionEvent
from portfolio_common.database_models import PositionState
from src.services.calculators.position_calculator.app.core.position_logic import PositionCalculator
from src.services.calculators.position_calculator.app.repositories.position_repository import PositionRepository
from portfolio_common.position_state_repository import PositionStateRepository

pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_repo() -> AsyncMock:
    """Provides a mock PositionRepository."""
    repo = AsyncMock(spec=PositionRepository)
    repo.get_transactions_on_or_after.return_value = []
    repo.get_last_position_before.return_value = None
    return repo

@pytest.fixture
def mock_state_repo() -> AsyncMock:
    """Provides a mock PositionStateRepository."""
    repo = AsyncMock(spec=PositionStateRepository)
    return repo

@pytest.fixture
def sample_event() -> TransactionEvent:
    """Provides a sample transaction event."""
    return TransactionEvent(
        transaction_id="T1", portfolio_id="P1", instrument_id="I1", security_id="S1",
        transaction_date=datetime(2025, 8, 20), transaction_type="BUY", quantity=Decimal("50"),
        price=Decimal("110"), gross_transaction_amount=Decimal("5500"),
        trade_currency="USD", currency="USD", net_cost=Decimal("5505")
    )


async def test_calculate_normal_flow(
    mock_repo: AsyncMock,
    mock_state_repo: AsyncMock,
    sample_event: TransactionEvent
):
    """
    GIVEN a transaction that is NOT backdated
    WHEN PositionCalculator.calculate runs
    THEN it should proceed with the standard position calculation logic.
    """
    # ARRANGE: Simulate a state where the transaction is not backdated
    current_state = PositionState(watermark_date=date(2025, 8, 19), epoch=0)
    mock_state_repo.get_or_create_state.return_value = current_state
    mock_repo.get_transactions_on_or_after.return_value = [sample_event]

    # ACT
    await PositionCalculator.calculate(sample_event, AsyncMock(), mock_repo, mock_state_repo)

    # ASSERT
    mock_state_repo.get_or_create_state.assert_awaited_once_with("P1", "S1")
    # Verify it did NOT trigger reprocessing
    mock_state_repo.increment_epoch_and_reset_watermark.assert_not_called()
    # Verify it continued with the calculation
    mock_repo.save_positions.assert_awaited_once()


async def test_calculate_triggers_reprocessing_for_backdated_transaction(
    mock_repo: AsyncMock,
    mock_state_repo: AsyncMock,
    sample_event: TransactionEvent
):
    """
    GIVEN a transaction that IS backdated
    WHEN PositionCalculator.calculate runs
    THEN it should increment the epoch and reset the watermark.
    """
    # ARRANGE: The watermark is AFTER the transaction date, making it backdated
    current_state = PositionState(watermark_date=date(2025, 8, 25), epoch=0)
    mock_state_repo.get_or_create_state.return_value = current_state
    
    # ACT
    await PositionCalculator.calculate(sample_event, AsyncMock(), mock_repo, mock_state_repo)

    # ASSERT
    mock_state_repo.get_or_create_state.assert_awaited_once_with("P1", "S1")
    # Verify it triggered the reprocessing state change
    mock_state_repo.increment_epoch_and_reset_watermark.assert_awaited_once_with(
        "P1", "S1", date(2025, 8, 19) # new watermark = txn_date - 1 day
    )
    # Verify it did NOT continue with the normal calculation flow
    mock_repo.save_positions.assert_not_called()