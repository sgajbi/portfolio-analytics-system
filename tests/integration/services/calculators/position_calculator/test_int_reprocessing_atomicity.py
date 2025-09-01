# tests/integration/services/calculators/position_calculator/test_int_reprocessing_atomicity.py
import pytest
from unittest.mock import MagicMock, AsyncMock
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from portfolio_common.database_models import Portfolio, Instrument, Transaction as DBTransaction, PositionState, DailyPositionSnapshot, OutboxEvent
from portfolio_common.events import TransactionEvent
from portfolio_common.position_state_repository import PositionStateRepository
from portfolio_common.outbox_repository import OutboxRepository
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

async def test_reprocessing_is_atomic_on_outbox_failure(
    setup_repro_atomicity_data,
    async_db_session: AsyncSession,
    db_engine
):
    """
    This test verifies the new atomic implementation.
    It simulates a crash during the outbox creation step and asserts that
    the entire database transaction is rolled back, leaving the system in a
    consistent state.
    """
    # ARRANGE: Instantiate real repositories and a failing OutboxRepository
    repo = PositionRepository(async_db_session)
    position_state_repo = PositionStateRepository(async_db_session)
    outbox_repo = OutboxRepository(async_db_session)
    
    # Mock the outbox repo to fail, simulating a DB constraint violation or other error
    outbox_repo.create_outbox_event = AsyncMock(side_effect=Exception("Outbox failed!"))

    back_dated_event = TransactionEvent(
        transaction_id="TXN_ATOM_BACKDATED", portfolio_id=PORTFOLIO_ID, instrument_id="ATS",
        security_id=SECURITY_ID, transaction_date=datetime(2025, 9, 5, 10),
        transaction_type="BUY", quantity=10, price=9, gross_transaction_amount=90,
        trade_currency="USD", currency="USD", epoch=None # An original event has no epoch
    )

    # ACT: Attempt to process the back-dated event, which should fail
    with pytest.raises(Exception, match="Outbox failed!"):
        # --- THIS IS THE FIX ---
        # The `reprocess_epoch` argument was removed from the method signature.
        await PositionCalculator.calculate(
            event=back_dated_event,
            db_session=async_db_session,
            repo=repo,
            position_state_repo=position_state_repo,
            outbox_repo=outbox_repo
        )
        # --- END FIX ---

    # ASSERT: Check the database state in a new, clean session
    sync_url = db_engine.url
    async_url = sync_url.render_as_string(hide_password=False).replace("postgresql://", "postgresql+asyncpg://")
    async_engine = create_async_engine(async_url)
    NewSession = async_sessionmaker(bind=async_engine, class_=AsyncSession, expire_on_commit=False)
    
    async with NewSession() as new_session:
        state_after_failure = await new_session.get(PositionState, (PORTFOLIO_ID, SECURITY_ID))
        outbox_count = await new_session.execute(select(func.count()).select_from(OutboxEvent))
        outbox_count = outbox_count.scalar()

    await async_engine.dispose()

    # With the fix, the transaction should roll back, leaving the state unchanged.
    assert state_after_failure is not None
    assert state_after_failure.epoch == 0
    assert state_after_failure.status == 'CURRENT'
    assert outbox_count == 0