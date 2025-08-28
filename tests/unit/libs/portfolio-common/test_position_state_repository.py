# tests/unit/libs/portfolio-common/test_position_state_repository.py
import pytest
from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession
from portfolio_common.database_models import PositionState
from portfolio_common.position_state_repository import PositionStateRepository

pytestmark = pytest.mark.asyncio


async def test_get_or_create_state_creates_new_record(
    clean_db, async_db_session: AsyncSession
):
    """
    GIVEN an empty database
    WHEN get_or_create_state is called for a new key
    THEN it should create and return a new state with default values.
    """
    # ARRANGE
    repo = PositionStateRepository(async_db_session)
    portfolio_id = "STATE_P1"
    security_id = "STATE_S1"

    # ACT
    state = await repo.get_or_create_state(portfolio_id, security_id)
    await async_db_session.commit()

    # ASSERT
    assert state is not None
    assert state.portfolio_id == portfolio_id
    assert state.security_id == security_id
    assert state.epoch == 0
    assert state.watermark_date == date(1970, 1, 1)
    assert state.status == 'CURRENT'

async def test_get_or_create_state_is_idempotent(
    clean_db, async_db_session: AsyncSession
):
    """
    GIVEN an existing state record
    WHEN get_or_create_state is called again for the same key
    THEN it should return the existing state without altering it.
    """
    # ARRANGE
    repo = PositionStateRepository(async_db_session)
    portfolio_id = "STATE_P1"
    security_id = "STATE_S1"
    
    # Call it once to create the initial state
    initial_state = await repo.get_or_create_state(portfolio_id, security_id)
    await async_db_session.commit()
    
    # ACT: Call it a second time
    second_state = await repo.get_or_create_state(portfolio_id, security_id)
    await async_db_session.commit()

    # ASSERT
    assert second_state.epoch == initial_state.epoch
    assert second_state.watermark_date == initial_state.watermark_date
    assert second_state.status == initial_state.status

async def test_increment_epoch_and_reset_watermark(
    clean_db, async_db_session: AsyncSession
):
    """
    GIVEN an existing state record
    WHEN increment_epoch_and_reset_watermark is called
    THEN it should increment the epoch, update the watermark, and set status to REPROCESSING.
    """
    # ARRANGE
    repo = PositionStateRepository(async_db_session)
    portfolio_id = "STATE_P1"
    security_id = "STATE_S1"
    new_watermark = date(2025, 5, 9)
    
    # Create the initial state
    await repo.get_or_create_state(portfolio_id, security_id)
    await async_db_session.commit()

    # ACT
    updated_state = await repo.increment_epoch_and_reset_watermark(
        portfolio_id, security_id, new_watermark
    )
    await async_db_session.commit()
    
    # ASSERT
    assert updated_state.epoch == 1
    assert updated_state.watermark_date == new_watermark
    assert updated_state.status == 'REPROCESSING'

    # Verify the change was persisted
    fetched_state = await async_db_session.get(PositionState, (portfolio_id, security_id))
    assert fetched_state.epoch == 1

async def test_update_watermarks_if_older(
    clean_db, async_db_session: AsyncSession
):
    """
    GIVEN multiple existing state records
    WHEN update_watermarks_if_older is called
    THEN it should only update the records where the new watermark is older.
    """
    # ARRANGE
    repo = PositionStateRepository(async_db_session)
    keys_to_update = [("P1", "S1"), ("P2", "S2"), ("P3", "S3")]
    
    # P1: Watermark is newer, should be updated
    state1 = PositionState(portfolio_id="P1", security_id="S1", watermark_date=date(2025, 6, 15), epoch=0, status='CURRENT')
    # P2: Watermark is older, should NOT be updated
    state2 = PositionState(portfolio_id="P2", security_id="S2", watermark_date=date(2025, 5, 1), epoch=0, status='CURRENT')
    # P3: Watermark is newer, should be updated
    state3 = PositionState(portfolio_id="P3", security_id="S3", watermark_date=date(2025, 8, 1), epoch=0, status='CURRENT')
    
    async_db_session.add_all([state1, state2, state3])
    await async_db_session.commit()

    # ACT
    new_watermark = date(2025, 6, 10)
    updated_count = await repo.update_watermarks_if_older(keys_to_update, new_watermark)
    await async_db_session.commit()

    # ASSERT
    assert updated_count == 2
    
    p1_state = await async_db_session.get(PositionState, ("P1", "S1"))
    assert p1_state.watermark_date == new_watermark
    assert p1_state.status == 'REPROCESSING'
    
    p2_state = await async_db_session.get(PositionState, ("P2", "S2"))
    assert p2_state.watermark_date == date(2025, 5, 1) # Unchanged
    assert p2_state.status == 'CURRENT' # Unchanged
    
    p3_state = await async_db_session.get(PositionState, ("P3", "S3"))
    assert p3_state.watermark_date == new_watermark
    assert p3_state.status == 'REPROCESSING'

async def test_bulk_update_states(clean_db, async_db_session: AsyncSession):
    """
    GIVEN a list of state updates
    WHEN bulk_update_states is called
    THEN it should update all corresponding records in a single atomic operation.
    """
    # ARRANGE
    repo = PositionStateRepository(async_db_session)
    
    state1 = PositionState(portfolio_id="P1", security_id="S1", watermark_date=date(2025, 6, 1), epoch=1, status='REPROCESSING')
    state2 = PositionState(portfolio_id="P2", security_id="S2", watermark_date=date(2025, 6, 1), epoch=2, status='REPROCESSING')
    async_db_session.add_all([state1, state2])
    await async_db_session.commit()
    
    updates = [
        {"portfolio_id": "P1", "security_id": "S1", "watermark_date": date(2025, 6, 15), "status": "CURRENT"},
        {"portfolio_id": "P2", "security_id": "S2", "watermark_date": date(2025, 6, 20), "status": "REPROCESSING"},
    ]

    # ACT
    updated_count = await repo.bulk_update_states(updates)
    await async_db_session.commit()

    # ASSERT
    assert updated_count == 2
    
    p1_state = await async_db_session.get(PositionState, ("P1", "S1"))
    assert p1_state.watermark_date == date(2025, 6, 15)
    assert p1_state.status == 'CURRENT'
    
    p2_state = await async_db_session.get(PositionState, ("P2", "S2"))
    assert p2_state.watermark_date == date(2025, 6, 20)
    assert p2_state.status == 'REPROCESSING'