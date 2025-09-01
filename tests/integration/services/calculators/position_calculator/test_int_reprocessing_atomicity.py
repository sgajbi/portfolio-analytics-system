# tests/integration/services/calculators/position_calculator/test_int_reprocessing_atomicity.py
import pytest
from unittest.mock import MagicMock
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import Session

from portfolio_common.database_models import Portfolio, Instrument, Transaction as DBTransaction, PositionState, DailyPositionSnapshot
from portfolio_common.events import TransactionEvent
from portfolio_common.kafka_utils import KafkaProducer
from portfolio_common.position_state_repository import PositionStateRepository
from src.services.calculators.position_calculator.app.repositories.position_repository import PositionRepository
from src.services.calculators.position_calculator.app.core.position_logic import PositionCalculator

pytestmark = pytest.mark.asyncio

PORTFOLIO_ID = "E2E_REPRO_ATOM_01"
SECURITY_ID = "SEC_REPRO_ATOM_01"

@pytest.fixture(scope="function")
def setup_repro_atomicity_data(db_engine, clean_db):
    """
    Sets up a simple, valid initial state for a position, ready to be reprocessed.
    """
    with Session(db_engine) as session:
        # Prerequisites
        session.add(Portfolio(portfolio_id=PORTFOLIO_ID, base_currency="USD", open_date=date(2025, 1, 1), cif_id="CIF", status="ACTIVE", risk_exposure="a", investment_time_horizon="b", portfolio_type="c", booking_center="d"))
        
        session.add(Instrument(
            security_id=SECURITY_ID, 
            name="Atomicity Test Stock", 
            isin="US_ATOM_REPRO", 
            currency="USD",
            product_type="Equity"
        ))

        session.flush()

        # Initial State
        session.add(DBTransaction(transaction_id="TXN_ATOM_1", portfolio_id=PORTFOLIO_ID, instrument_id="ATS", security_id=SECURITY_ID, transaction_date=datetime(2025, 9, 10, 10), transaction_type="BUY", quantity=100, price=10, gross_transaction_amount=1000, trade_currency="USD", currency="USD"))
        session.add(PositionState(portfolio_id=PORTFOLIO_ID, security_id=SECURITY_ID, epoch=0, watermark_date=date(2025, 9, 9), status='CURRENT'))
        session.add(DailyPositionSnapshot(portfolio_id=PORTFOLIO_ID, security_id=SECURITY_ID, date=date(2025, 9, 10), epoch=0, quantity=100, cost_basis=1000))
        session.commit()

async def test_reprocessing_is_not_atomic_on_publish_failure(
    setup_repro_atomicity_data,
    async_db_session: AsyncSession,
    db_engine # <-- Add db_engine fixture to create a new session
):
    """
    This test proves the current implementation is NOT atomic.
    It simulates a crash during Kafka publishing and asserts that the database
    is left in an inconsistent state (epoch incremented, but no events sent).
    This test will fail after the fix is applied, and the assertion will be flipped.
    """
    # ARRANGE: Instantiate real repositories and a failing Kafka producer
    repo = PositionRepository(async_db_session)
    position_state_repo = PositionStateRepository(async_db_session)
    
    mock_kafka_producer = MagicMock(spec=KafkaProducer)
    mock_kafka_producer.publish_message.side_effect = Exception("Kafka is down!")

    # This is the back-dated event that will trigger the reprocessing
    back_dated_event = TransactionEvent(
        transaction_id="TXN_ATOM_BACKDATED", portfolio_id=PORTFOLIO_ID, instrument_id="ATS",
        security_id=SECURITY_ID, transaction_date=datetime(2025, 9, 5, 10),
        transaction_type="BUY", quantity=10, price=9, gross_transaction_amount=90,
        trade_currency="USD", currency="USD", epoch=0
    )

    # ACT: Attempt to process the back-dated event, which should fail
    with pytest.raises(Exception, match="Kafka is down!"):
        await PositionCalculator.calculate(
            event=back_dated_event,
            db_session=async_db_session,
            repo=repo,
            position_state_repo=position_state_repo,
            kafka_producer=mock_kafka_producer,
            reprocess_epoch=None
        )

    # --- FIX: Create a new, clean session factory to check the committed DB state ---
    sync_url = db_engine.url
    async_url = sync_url.render_as_string(hide_password=False).replace("postgresql://", "postgresql+asyncpg://")
    async_engine = create_async_engine(async_url)
    NewSession = async_sessionmaker(bind=async_engine, class_=AsyncSession, expire_on_commit=False)
    # --- END FIX ---

    # ASSERT: Check the database state in a new, clean session to see what was committed.
    async with NewSession() as new_session:
        state_after_failure = await new_session.get(PositionState, (PORTFOLIO_ID, SECURITY_ID))

    await async_engine.dispose()

    # The current (buggy) implementation commits the state change before publishing.
    # This assertion proves the bug: the epoch is now 1, but the replay failed.
    # The system is now stuck in a bad state.
    assert state_after_failure is not None
    assert state_after_failure.epoch == 1
    assert state_after_failure.status == 'REPROCESSING'