# tests/unit/services/calculators/position_calculator/core/test_position_logic.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import date, datetime, timedelta
from decimal import Decimal

from portfolio_common.events import TransactionEvent
from portfolio_common.database_models import PositionState, Transaction as DBTransaction
from src.services.calculators.position_calculator.app.core.position_logic import PositionCalculator
from src.services.calculators.position_calculator.app.repositories.position_repository import PositionRepository
from portfolio_common.position_state_repository import PositionStateRepository
from portfolio_common.kafka_utils import KafkaProducer

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
    headers_dict = {key: value for key, value in first_call_args['headers']}
    assert headers_dict['reprocess_epoch'] == b'1'

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
    # This state would normally trigger reprocessing, but the epoch header should prevent it.
    current_state = PositionState(watermark_date=date(2025, 8, 25), epoch=1) 
    mock_state_repo.get_or_create_state.return_value = current_state
    mock_repo.get_transactions_on_or_after.return_value = [sample_event]

    # ACT
    await PositionCalculator.calculate(
        sample_event, AsyncMock(), mock_repo, mock_state_repo, mock_kafka_producer, reprocess_epoch=1
    )

    # ASSERT
    # The key assertion: The reprocessing logic was NOT triggered for a replayed event.
    mock_state_repo.increment_epoch_and_reset_watermark.assert_not_called()
    mock_repo.get_all_transactions_for_security.assert_not_called()

    # The normal calculation logic SHOULD have been called.
    mock_repo.save_positions.assert_awaited_once()