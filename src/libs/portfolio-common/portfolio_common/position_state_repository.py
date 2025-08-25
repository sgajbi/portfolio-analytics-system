# src/libs/portfolio-common/portfolio_common/position_state_repository.py
import logging
from datetime import date
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .database_models import PositionState
from .utils import async_timed

logger = logging.getLogger(__name__)

class PositionStateRepository:
    """
    Handles database operations for the PositionState model, which tracks
    the epoch and watermark for each (portfolio_id, security_id) key.
    """
    def __init__(self, db: AsyncSession):
        self.db = db

    @async_timed(repository="PositionStateRepository", method="get_or_create_state")
    async def get_or_create_state(self, portfolio_id: str, security_id: str) -> PositionState:
        """
        Retrieves the state for a key. If it doesn't exist, it creates it
        with default values (epoch 0, and a far-past watermark date).
        This operation is idempotent.
        """
        stmt = pg_insert(PositionState).values(
            portfolio_id=portfolio_id,
            security_id=security_id,
            epoch=0,
            watermark_date=date(1970, 1, 1), # A safe default minimum date
            status='CURRENT'
        ).on_conflict_do_nothing(
            index_elements=['portfolio_id', 'security_id']
        )
        await self.db.execute(stmt)
        
        select_stmt = select(PositionState).filter_by(
            portfolio_id=portfolio_id,
            security_id=security_id
        )
        result = await self.db.execute(select_stmt)
        return result.scalar_one()

    @async_timed(repository="PositionStateRepository", method="increment_epoch_and_reset_watermark")
    async def increment_epoch_and_reset_watermark(
        self,
        portfolio_id: str,
        security_id: str,
        new_watermark_date: date
    ) -> PositionState:
        """
        Atomically increments the epoch, resets the watermark date, and sets the
        status to 'REPROCESSING' for a given key. Returns the updated state.
        """
        stmt = (
            update(PositionState)
            .where(
                PositionState.portfolio_id == portfolio_id,
                PositionState.security_id == security_id
            )
            .values(
                epoch=PositionState.epoch + 1,
                watermark_date=new_watermark_date,
                status='REPROCESSING'
            )
            .returning(PositionState)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one()