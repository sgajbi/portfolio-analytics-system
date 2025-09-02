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
from portfolio_common.monitoring import REPROCESSING_EPOCH_BUMPED_TOTAL

# The module-level pytestmark is removed to apply the asyncio mark selectively.

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

@pytest.mark.asyncio
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
    mock_fencer_instance.check = AsyncMock(return_value=False)

    # ACT
    await PositionCalculator.calculate(
        sample_event, AsyncMock(), mock_repo, mock_state_repo, mock_outbox_repo
    )

    # ASSERT
    mock_fencer_instance.check.assert_awaited_once_with(sample_event)
    mock_state_repo.increment_epoch_and_reset_watermark.assert_not_called()
    mock_repo.save_positions.assert_not_called()
    mock_outbox_repo.create_outbox_event.assert_not_called()


@pytest.mark.asyncio
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
    mock_fencer_instance.check = AsyncMock(return_value=True)

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

@pytest.mark.asyncio
@patch("src.services.calculators.position_calculator.app.core.position_logic.REPROCESSING_EPOCH_BUMPED_TOTAL")
@patch("src.services.calculators.position_calculator.app.core.position_logic.EpochFencer")
async def test_calculate_re_emits_and_increments_metric_for_backdated_event(
    mock_fencer_class: MagicMock,
    mock_metric: MagicMock,
    mock_repo: AsyncMock,
    mock_state_repo: AsyncMock,
    mock_outbox_repo: AsyncMock,
    sample_event: TransactionEvent
):
    """
    GIVEN a transaction that IS backdated
    WHEN PositionCalculator.calculate runs for an original event (epoch is None)
    THEN it should increment epoch, re-emit all historical events plus the triggering event.
    """
    # ARRANGE
    mock_fencer_instance = mock_fencer_class.return_value
    mock_fencer_instance.check = AsyncMock(return_value=True)
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
    
    # Assert that the metric was instrumented correctly
    mock_metric.labels.assert_called_once_with(portfolio_id="P1", security_id="S1")
    mock_metric.labels.return_value.inc.assert_called_once()
    
    # Assert that it tried to publish TWO events: one historical + the triggering one
    assert mock_outbox_repo.create_outbox_event.call_count == 2
    
    # Check that both events were tagged with the new epoch
    first_call_args = mock_outbox_repo.create_outbox_event.call_args_list[0].kwargs
    assert first_call_args['payload']['epoch'] == 1
    second_call_args = mock_outbox_repo.create_outbox_event.call_args_list[1].kwargs
    assert second_call_args['payload']['epoch'] == 1

def test_calculate_next_position_for_sell_uses_net_cost():
    """
    Verifies that for a SELL transaction, the cost basis is correctly reduced
    by the `net_cost` (COGS) from the event, not by a proportional amount.
    """
    # ARRANGE
    initial_state = PositionStateDTO(
        quantity=Decimal("100"),
        cost_basis=Decimal("1200"),
        cost_basis_local=Decimal("1000")
    )
    sell_event = TransactionEvent(
        transaction_id="SELL_FIFO_01",
        transaction_type="SELL",
        quantity=Decimal("50"),
        net_cost=Decimal("-550"),
        net_cost_local=Decimal("-500"),
        portfolio_id="P1", instrument_id="I1", security_id="S1",
        transaction_date=datetime.now(), price=Decimal(0),
        gross_transaction_amount=Decimal(0), trade_currency="USD", currency="USD"
    )

    # ACT
    new_state = PositionCalculator.calculate_next_position(initial_state, sell_event)

    # ASSERT
    assert new_state.quantity == Decimal("50")
    assert new_state.cost_basis == Decimal("650")
    assert new_state.cost_basis_local == Decimal("500")