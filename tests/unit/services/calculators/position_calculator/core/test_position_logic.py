# tests/unit/services/calculators/position_calculator/core/test_position_logic.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date, datetime, timedelta
from decimal import Decimal

from portfolio_common.events import TransactionEvent
from portfolio_common.database_models import PositionState, Transaction as DBTransaction
from src.services.calculators.position_calculator.app.core.position_logic import PositionCalculator
from src.services.calculators.position_calculator.app.core.position_models import PositionState as PositionStateDTO
from src.services.calculators.position_calculator.app.repositories.position_repository import PositionRepository
from portfolio_common.position_state_repository import PositionStateRepository
from portfolio_common.outbox_repository import OutboxRepository
from portfolio_common.reprocessing import EpochFencer

pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_repo() -> AsyncMock:
    """Provides a mock PositionRepository."""
    repo = AsyncMock(spec=PositionRepository)
    repo.get_transactions_on_or_after.return_value = []
    repo.get_last_position_before.return_value = None
    repo.get_latest_completed_snapshot_date.return_value = None
    return repo

@pytest.fixture
def mock_state_repo() -> AsyncMock:
    """Provides a mock PositionStateRepository."""
    repo = AsyncMock(spec=PositionStateRepository)
    return repo

@pytest.fixture
def mock_outbox_repo() -> AsyncMock:
    """Provides a mock OutboxRepository."""
    return AsyncMock(spec=OutboxRepository)

@pytest.fixture
def sample_event() -> TransactionEvent:
    """Provides a sample transaction event."""
    return TransactionEvent(
        transaction_id="T1", portfolio_id="P1", instrument_id="I1", security_id="S1",
        transaction_date=datetime(2025, 8, 20), transaction_type="BUY", quantity=Decimal("50"),
        price=Decimal("110"), gross_transaction_amount=Decimal("5500"),
        trade_currency="USD", currency="USD", net_cost=Decimal("5505"), epoch=1
    )

@patch("src.services.calculators.position_calculator.app.core.position_logic.EpochFencer")
async def test_calculate_discards_stale_epoch_event(
    mock_fencer_class: MagicMock,
    mock_repo: AsyncMock,
    mock_state_repo: AsyncMock,
    mock_outbox_repo: AsyncMock,
    sample_event: TransactionEvent
):
    """
    GIVEN an event that the EpochFencer deems stale
    WHEN PositionCalculator.calculate is called
    THEN it should not perform any calculations or repository writes.
    """
    # ARRANGE
    mock_fencer_instance = mock_fencer_class.return_value
    # --- THIS IS THE FIX ---
    # The mocked method must be an awaitable that returns a boolean.
    mock_fencer_instance.check = AsyncMock(return_value=False)
    # --- END FIX ---

    # ACT
    await PositionCalculator.calculate(
        sample_event, AsyncMock(), mock_repo, mock_state_repo, mock_outbox_repo
    )

    # ASSERT
    mock_fencer_instance.check.assert_awaited_once_with(sample_event)
    mock_state_repo.increment_epoch_and_reset_watermark.assert_not_called()
    mock_repo.save_positions.assert_not_called()
    mock_outbox_repo.create_outbox_event.assert_not_called()


@patch("src.services.calculators.position_calculator.app.core.position_logic.EpochFencer")
async def test_calculate_normal_flow(
    mock_fencer_class: MagicMock,
    mock_repo: AsyncMock,
    mock_state_repo: AsyncMock,
    mock_outbox_repo: AsyncMock,
    sample_event: TransactionEvent
):
    """
    GIVEN a transaction that is NOT backdated
    WHEN PositionCalculator.calculate runs
    THEN it should proceed with the standard position calculation logic.
    """
    # ARRANGE
    mock_fencer_instance = mock_fencer_class.return_value
    # --- THIS IS THE FIX ---
    mock_fencer_instance.check = AsyncMock(return_value=True)
    # --- END FIX ---

    # Simulate a state where the transaction is not backdated
    mock_state_repo.get_or_create_state.return_value = PositionState(watermark_date=date(2025, 8, 19), epoch=1)
    mock_repo.get_latest_completed_snapshot_date.return_value = None
    mock_repo.get_transactions_on_or_after.return_value = [sample_event]

    # ACT
    await PositionCalculator.calculate(
        sample_event, AsyncMock(), mock_repo, mock_state_repo, mock_outbox_repo
    )

    # ASSERT
    mock_fencer_instance.check.assert_awaited_once()
    mock_state_repo.increment_epoch_and_reset_watermark.assert_not_called()
    mock_repo.save_positions.assert_awaited_once()
    mock_outbox_repo.create_outbox_event.assert_not_called()

@patch("src.services.calculators.position_calculator.app.core.position_logic.EpochFencer")
async def test_calculate_re_emits_events_for_original_backdated_transaction(
    mock_fencer_class: MagicMock,
    mock_repo: AsyncMock,
    mock_state_repo: AsyncMock,
    mock_outbox_repo: AsyncMock,
    sample_event: TransactionEvent
):
    """
    GIVEN a transaction that IS backdated
    WHEN PositionCalculator.calculate runs for an original event (epoch is None)
    THEN it should increment epoch, reset watermark, and re-emit all historical events.
    """
    # ARRANGE
    mock_fencer_instance = mock_fencer_class.return_value
    # --- THIS IS THE FIX ---
    mock_fencer_instance.check = AsyncMock(return_value=True)
    # --- END FIX ---

    # This event is an original ingestion, so its epoch is not yet set.
    sample_event.epoch = None

    current_state = PositionState(watermark_date=date(2025, 8, 25), epoch=0)
    mock_state_repo.get_or_create_state.return_value = current_state
    
    new_state = PositionState(epoch=1)
    mock_state_repo.increment_epoch_and_reset_watermark.return_value = new_state
    
    mock_repo.get_all_transactions_for_security.return_value = [
        DBTransaction(transaction_id="TXN_HIST_1", portfolio_id="P1", security_id="S1", instrument_id="I1", transaction_date=datetime(2025, 1, 5), transaction_type="BUY", quantity=Decimal("1"), price=Decimal("1"), gross_transaction_amount=Decimal("1"), trade_currency="USD", currency="USD", trade_fee=Decimal("0")),
    ]

    # ACT
    await PositionCalculator.calculate(
        sample_event, AsyncMock(), mock_repo, mock_state_repo, mock_outbox_repo
    )

    # ASSERT
    mock_state_repo.increment_epoch_and_reset_watermark.assert_awaited_once_with(
        "P1", "S1", date(2025, 8, 19)
    )
    mock_repo.get_all_transactions_for_security.assert_awaited_once_with("P1", "S1")
    assert mock_outbox_repo.create_outbox_event.call_count == 1
    
    first_call_args = mock_outbox_repo.create_outbox_event.call_args_list[0].kwargs
    assert first_call_args['payload']['epoch'] == 1