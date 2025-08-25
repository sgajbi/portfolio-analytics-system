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