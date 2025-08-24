# tests/unit/services/calculators/position_calculator/core/test_position_logic.py
import pytest
from unittest.mock import AsyncMock
from datetime import date, datetime
from decimal import Decimal

from portfolio_common.events import TransactionEvent
from src.services.calculators.position_calculator.app.core.position_logic import PositionCalculator
from src.services.calculators.position_calculator.app.repositories.position_repository import PositionRepository

pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_repo() -> AsyncMock:
    """Provides a mock PositionRepository."""
    repo = AsyncMock(spec=PositionRepository)
    repo.get_transactions_on_or_after.return_value = []
    repo.get_last_position_before.return_value = None
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

async def test_calculate_creates_valuation_job_for_current_transaction(mock_repo: AsyncMock, sample_event: TransactionEvent):
    """
    GIVEN a transaction that is NOT backdated
    WHEN PositionCalculator.calculate runs
    THEN it should create a VALUATION job.
    """
    # ARRANGE: The latest business date is the same as the transaction date
    mock_repo.get_latest_business_date.return_value = date(2025, 8, 20)
    mock_repo.get_transactions_on_or_after.return_value = [sample_event] # Simulate finding the event itself

    # ACT
    await PositionCalculator.calculate(sample_event, AsyncMock(), mock_repo)

    # ASSERT
    mock_repo.upsert_valuation_job.assert_awaited_once()
    mock_repo.upsert_recalculation_job.assert_not_called()
    call_args = mock_repo.upsert_valuation_job.call_args.kwargs
    assert call_args['valuation_date'] == date(2025, 8, 20)

async def test_calculate_creates_recalculation_job_for_backdated_transaction(mock_repo: AsyncMock, sample_event: TransactionEvent):
    """
    GIVEN a transaction that IS backdated
    WHEN PositionCalculator.calculate runs
    THEN it should create a RECALCULATION job.
    """
    # ARRANGE: The latest business date is AFTER the transaction date
    mock_repo.get_latest_business_date.return_value = date(2025, 8, 25)
    mock_repo.get_transactions_on_or_after.return_value = [sample_event]

    # ACT
    await PositionCalculator.calculate(sample_event, AsyncMock(), mock_repo)

    # ASSERT
    mock_repo.upsert_recalculation_job.assert_awaited_once()
    mock_repo.upsert_valuation_job.assert_not_called()
    call_args = mock_repo.upsert_recalculation_job.call_args.kwargs
    assert call_args['from_date'] == date(2025, 8, 20)


async def test_calculate_creates_valuation_job_for_backdated_recalc_event(mock_repo: AsyncMock, sample_event: TransactionEvent):
    """
    GIVEN a transaction that IS backdated but is also part of a recalculation flow
    WHEN PositionCalculator.calculate runs
    THEN it should create a VALUATION job, breaking the infinite loop.
    """
    # ARRANGE
    mock_repo.get_latest_business_date.return_value = date(2025, 8, 25) # Backdated
    mock_repo.get_transactions_on_or_after.return_value = [sample_event]

    # ACT: Call with the is_recalculation_event flag set to True
    await PositionCalculator.calculate(
        sample_event, AsyncMock(), mock_repo, is_recalculation_event=True
    )

    # ASSERT: It should create a VALUATION job, not a recalculation job.
    mock_repo.upsert_valuation_job.assert_awaited_once()
    mock_repo.upsert_recalculation_job.assert_not_called()