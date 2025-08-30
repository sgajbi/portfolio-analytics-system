# tests/unit/services/calculators/position_calculator/core/test_position_logic.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import date, datetime, timedelta
from decimal import Decimal

from portfolio_common.events import TransactionEvent
from portfolio_common.database_models import PositionState, Transaction as DBTransaction
from src.services.calculators.position_calculator.app.core.position_logic import PositionCalculator
from src.services.calculators.position_calculator.app.core.position_models import PositionState as PositionStateDTO
from src.services.calculators.position_calculator.app.repositories.position_repository import PositionRepository
from portfolio_common.position_state_repository import PositionStateRepository
from portfolio_common.kafka_utils import KafkaProducer

# NOTE: pytestmark has been removed. Tests are marked individually.

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
def mock_kafka_producer() -> MagicMock:
    """Provides a mock KafkaProducer."""
    return MagicMock(spec=KafkaProducer)

@pytest.fixture
def sample_event() -> TransactionEvent:
    """Provides a sample transaction event."""
    return TransactionEvent(
        transaction_id="T1", portfolio_id="P1", instrument_id="I1", security_id="S1",
        transaction_date=datetime(2025, 8, 20), transaction_type="BUY", quantity=Decimal("50"),
        price=Decimal("110"), gross_transaction_amount=Decimal("5500"),
        trade_currency="USD", currency="USD", net_cost=Decimal("5505")
    )

@pytest.mark.asyncio
async def test_calculate_normal_flow(
    mock_repo: AsyncMock,
    mock_state_repo: AsyncMock,
    mock_kafka_producer: MagicMock,
    sample_event: TransactionEvent
):
    """
    GIVEN a transaction that is NOT backdated
    WHEN PositionCalculator.calculate runs for an original event (reprocess_epoch is None)
    THEN it should proceed with the standard position calculation logic.
    """
    # ARRANGE: Simulate a state where the transaction is not backdated
    current_state = PositionState(watermark_date=date(2025, 8, 19), epoch=0)
    mock_state_repo.get_or_create_state.return_value = current_state
    mock_repo.get_transactions_on_or_after.return_value = [sample_event]

    # ACT
    await PositionCalculator.calculate(
        sample_event, AsyncMock(), mock_repo, mock_state_repo, mock_kafka_producer, reprocess_epoch=None
    )

    # ASSERT
    mock_state_repo.increment_epoch_and_reset_watermark.assert_not_called()
    mock_repo.save_positions.assert_awaited_once()
    mock_kafka_producer.publish_message.assert_not_called()

@pytest.mark.asyncio
async def test_calculate_re_emits_events_for_original_backdated_transaction(
    mock_repo: AsyncMock,
    mock_state_repo: AsyncMock,
    mock_kafka_producer: MagicMock,
    sample_event: TransactionEvent
):
    """
    GIVEN a transaction that IS backdated
    WHEN PositionCalculator.calculate runs for an original event (reprocess_epoch is None)
    THEN it should increment epoch, reset watermark, and re-emit all historical events.
    """
    # ARRANGE
    current_state = PositionState(watermark_date=date(2025, 8, 25), epoch=0)
    mock_state_repo.get_or_create_state.return_value = current_state
    
    new_state = PositionState(epoch=1)
    mock_state_repo.increment_epoch_and_reset_watermark.return_value = new_state
    
    mock_repo.get_all_transactions_for_security.return_value = [
        DBTransaction(transaction_id="TXN_HIST_1", portfolio_id="P1", security_id="S1", instrument_id="I1", transaction_date=datetime(2025, 1, 5), transaction_type="BUY", quantity=Decimal("1"), price=Decimal("1"), gross_transaction_amount=Decimal("1"), trade_currency="USD", currency="USD", trade_fee=Decimal("0")),
        DBTransaction(transaction_id="TXN_HIST_2", portfolio_id="P1", security_id="S1", instrument_id="I1", transaction_date=datetime(2025, 2, 5), transaction_type="BUY", quantity=Decimal("1"), price=Decimal("1"), gross_transaction_amount=Decimal("1"), trade_currency="USD", currency="USD", trade_fee=Decimal("0"))
    ]

    # ACT
    await PositionCalculator.calculate(
        sample_event, AsyncMock(), mock_repo, mock_state_repo, mock_kafka_producer, reprocess_epoch=None
    )

    # ASSERT
    mock_state_repo.increment_epoch_and_reset_watermark.assert_awaited_once_with(
        "P1", "S1", date(2025, 8, 19)
    )
    mock_repo.get_all_transactions_for_security.assert_awaited_once_with("P1", "S1")
    assert mock_kafka_producer.publish_message.call_count == 2
    mock_kafka_producer.flush.assert_called_once()
    
    first_call_args = mock_kafka_producer.publish_message.call_args_list[0].kwargs
    assert first_call_args['value']['epoch'] == 1

@pytest.mark.asyncio
async def test_calculate_bypasses_back_dating_check_for_replayed_event(
    mock_repo: AsyncMock,
    mock_state_repo: AsyncMock,
    mock_kafka_producer: MagicMock,
    sample_event: TransactionEvent
):
    """
    GIVEN a transaction that IS backdated
    WHEN PositionCalculator.calculate runs for a REPLAYED event (reprocess_epoch is not None)
    THEN it should BYPASS the reprocessing trigger and proceed to normal calculation.
    """
    # ARRANGE
    current_state = PositionState(watermark_date=date(2025, 8, 25), epoch=1) 
    mock_state_repo.get_or_create_state.return_value = current_state
    mock_repo.get_transactions_on_or_after.return_value = [sample_event]

    # ACT
    await PositionCalculator.calculate(
        sample_event, AsyncMock(), mock_repo, mock_state_repo, mock_kafka_producer, reprocess_epoch=1
    )

    # ASSERT
    mock_state_repo.increment_epoch_and_reset_watermark.assert_not_called()
    mock_repo.get_all_transactions_for_security.assert_not_called()
    mock_repo.save_positions.assert_awaited_once()

@pytest.mark.asyncio
async def test_back_dated_check_uses_snapshot_date_when_watermark_is_stale(
    mock_repo: AsyncMock,
    mock_state_repo: AsyncMock,
    mock_kafka_producer: MagicMock,
    sample_event: TransactionEvent
):
    """
    GIVEN a back-dated transaction (date is 2025-08-20)
    AND the position_state watermark is stale (1970-01-01)
    BUT a daily snapshot exists for a later date (2025-08-22)
    WHEN PositionCalculator.calculate runs for this original event
    THEN it should correctly identify it as back-dated and trigger reprocessing.
    """
    # ARRANGE
    current_state = PositionState(watermark_date=date(1970, 1, 1), epoch=0, status='CURRENT')
    mock_state_repo.get_or_create_state.return_value = current_state
    latest_snapshot_date = date(2025, 8, 22)
    mock_repo.get_latest_completed_snapshot_date.return_value = latest_snapshot_date
    mock_state_repo.increment_epoch_and_reset_watermark.return_value = PositionState(epoch=1)
    mock_repo.get_all_transactions_for_security.return_value = []

    # ACT
    await PositionCalculator.calculate(
        event=sample_event,
        db_session=AsyncMock(),
        repo=mock_repo,
        position_state_repo=mock_state_repo,
        kafka_producer=mock_kafka_producer,
        reprocess_epoch=None
    )

    # ASSERT
    mock_repo.get_latest_completed_snapshot_date.assert_awaited_once_with("P1", "S1", 0)
    mock_state_repo.increment_epoch_and_reset_watermark.assert_awaited_once()
    mock_repo.get_all_transactions_for_security.assert_awaited_once()
    mock_kafka_producer.flush.assert_called_once()

@pytest.mark.asyncio
async def test_same_day_transaction_is_not_backdated(
    mock_repo: AsyncMock,
    mock_state_repo: AsyncMock,
    mock_kafka_producer: MagicMock,
    sample_event: TransactionEvent
):
    """
    GIVEN a transaction date that is THE SAME AS the effective completed date
    WHEN PositionCalculator.calculate runs
    THEN it should NOT be considered back-dated and should process normally.
    """
    # ARRANGE
    current_state = PositionState(watermark_date=date(2025, 8, 20), epoch=0)
    mock_state_repo.get_or_create_state.return_value = current_state
    mock_repo.get_latest_completed_snapshot_date.return_value = None
    mock_repo.get_transactions_on_or_after.return_value = [sample_event]

    # ACT
    await PositionCalculator.calculate(
        sample_event, AsyncMock(), mock_repo, mock_state_repo, mock_kafka_producer, reprocess_epoch=None
    )

    # ASSERT
    mock_state_repo.increment_epoch_and_reset_watermark.assert_not_called()
    mock_repo.save_positions.assert_awaited_once()

# --- NEW FAILING TEST (TDD) ---
def test_calculate_next_position_for_transfer_in_uses_quantity_field():
    """
    GIVEN a TRANSFER_IN transaction where quantity and gross amount differ
    WHEN calculate_next_position is called
    THEN the new position's quantity should be incremented by the `quantity` field,
    NOT the `gross_transaction_amount`.
    """
    # ARRANGE
    initial_state = PositionStateDTO(quantity=Decimal("0"), cost_basis=Decimal("0"))
    
    transfer_in_event = TransactionEvent(
        transaction_id="T_IN_1", portfolio_id="P1", instrument_id="I1", security_id="S1",
        transaction_date=datetime(2025, 8, 21), transaction_type="TRANSFER_IN", 
        quantity=Decimal("100"),
        price=Decimal("150"),
        gross_transaction_amount=Decimal("15000"),
        trade_currency="USD", currency="USD"
    )

    # ACT
    new_state = PositionCalculator.calculate_next_position(initial_state, transfer_in_event)
    
    # ASSERT
    assert new_state.quantity == Decimal("100")
    assert new_state.cost_basis == Decimal("15000")