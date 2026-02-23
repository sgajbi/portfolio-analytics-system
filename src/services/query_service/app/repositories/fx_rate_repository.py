# services/query-service/app/repositories/fx_rate_repository.py
import logging
from datetime import date
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from portfolio_common.database_models import FxRate

logger = logging.getLogger(__name__)


class FxRateRepository:
    """
    Handles read-only database queries for FX rate data.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_fx_rates(
        self,
        from_currency: str,
        to_currency: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[FxRate]:
        """
        Retrieves a list of FX rates for a currency pair, with optional
        date range filtering.
        """
        stmt = select(FxRate).filter_by(from_currency=from_currency, to_currency=to_currency)

        if start_date:
            stmt = stmt.filter(FxRate.rate_date >= start_date)

        if end_date:
            stmt = stmt.filter(FxRate.rate_date <= end_date)

        results = await self.db.execute(stmt.order_by(FxRate.rate_date.asc()))
        fx_rates = results.scalars().all()
        logger.info(
            f"Found {len(fx_rates)} FX rates for '{from_currency}-{to_currency}' with given filters."
        )
        return fx_rates
