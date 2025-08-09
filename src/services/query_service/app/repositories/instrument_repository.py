# services/query-service/app/repositories/instrument_repository.py
import logging
from typing import List, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from portfolio_common.database_models import Instrument

logger = logging.getLogger(__name__)

class InstrumentRepository:
    """
    Handles read-only database queries for instrument data.
    """
    def __init__(self, db: AsyncSession):
        self.db = db

    def _get_base_query(
        self,
        security_id: Optional[str] = None,
        product_type: Optional[str] = None
    ):
        """
        Constructs a base query with all the common filters.
        """
        stmt = select(Instrument)
        if security_id:
            stmt = stmt.filter_by(security_id=security_id)
        if product_type:
            stmt = stmt.filter_by(product_type=product_type)
        return stmt

    async def get_instruments(
        self,
        skip: int,
        limit: int,
        security_id: Optional[str] = None,
        product_type: Optional[str] = None
    ) -> List[Instrument]:
        """
        Retrieves a paginated list of instruments with optional filters.
        """
        stmt = self._get_base_query(security_id, product_type)
        results = await self.db.execute(stmt.order_by(Instrument.name.asc()).offset(skip).limit(limit))
        instruments = results.scalars().all()
        logger.info(f"Found {len(instruments)} instruments with given filters.")
        return instruments

    async def get_instruments_count(
        self,
        security_id: Optional[str] = None,
        product_type: Optional[str] = None
    ) -> int:
        """
        Returns the total count of instruments for the given filters.
        """
        stmt = self._get_base_query(security_id, product_type)
        count_stmt = select(func.count()).select_from(stmt.subquery())
        count = (await self.db.execute(count_stmt)).scalar()
        return count