# services/calculators/position-valuation-calculator/app/repositories/valuation_repository.py
import logging
from datetime import date
from typing import List, Optional
from sqlalchemy import select, func, distinct, exists
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import aliased

from portfolio_common.database_models import (
    PositionHistory, MarketPrice, DailyPositionSnapshot, FxRate, Instrument, Portfolio, Transaction
)
from portfolio_common.utils import async_timed

logger = logging.getLogger(__name__)

class ValuationRepository:
    """
    Handles all database interactions for the position valuation service.
    """
    def __init__(self, db: AsyncSession):
        self.db = db

    async def has_any_history_for_security(self, security_id: str) -> bool:
        """
        Checks if any transactional history (BUY/SELL) exists for a security.
        This is the definitive check for whether a position should eventually exist.
        """
        stmt = select(
            exists().where(
                Transaction.security_id == security_id,
                Transaction.transaction_type.in_(['BUY', 'SELL'])
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar()

    @async_timed(repository="ValuationRepository", method="get_portfolio")
    async def get_portfolio(self, portfolio_id: str) -> Optional[Portfolio]:
        """Fetches a portfolio by its ID."""
        stmt = select(Portfolio).filter_by(portfolio_id=portfolio_id)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    @async_timed(repository="ValuationRepository", method="get_instrument")
    async def get_instrument(self, security_id: str) -> Optional[Instrument]:
        """Fetches an instrument by its security ID."""
        stmt = select(Instrument).filter_by(security_id=security_id)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    @async_timed(repository="ValuationRepository", method="get_fx_rate")
    async def get_fx_rate(self, from_currency: str, to_currency: str, a_date: date) -> Optional[FxRate]:
        """Fetches the latest FX rate on or before a given date."""
        stmt = select(FxRate).filter(
            FxRate.from_currency == from_currency,
            FxRate.to_currency == to_currency,
            FxRate.rate_date <= a_date
        ).order_by(FxRate.rate_date.desc())
        result = await self.db.execute(stmt)
        return result.scalars().first()

    @async_timed(repository="ValuationRepository", method="get_latest_price_for_position")
    async def get_latest_price_for_position(self, security_id: str, position_date: date) -> Optional[MarketPrice]:
        """
        Finds the most recent market price for a given security on or before the position's date.
        """
        stmt = select(MarketPrice).filter(
            MarketPrice.security_id == security_id,
            MarketPrice.price_date <= position_date
        ).order_by(MarketPrice.price_date.desc())
        result = await self.db.execute(stmt)
        return result.scalars().first()
    
    @async_timed(repository="ValuationRepository", method="find_snapshots_to_update")
    async def find_snapshots_to_update(self, security_id: str, a_date: date) -> List[DailyPositionSnapshot]:
        """
        Finds all snapshots for a security on a given date. This is typically used
        by the MarketPriceConsumer to find positions that need re-valuation.
        """
        stmt = select(DailyPositionSnapshot).filter(
            DailyPositionSnapshot.security_id == security_id,
            DailyPositionSnapshot.date == a_date,
            DailyPositionSnapshot.quantity > 0
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

    @async_timed(repository="ValuationRepository", method="find_portfolios_holding_security_before_date")
    async def find_portfolios_holding_security_before_date(self, security_id: str, a_date: date) -> List[DailyPositionSnapshot]:
        """
        Finds the single latest daily snapshot for each portfolio that held a given security
        at any point before the specified date. This is used to roll forward positions.
        """
        ranked_snapshots_subq = select(
            DailyPositionSnapshot,
            func.row_number().over(
                partition_by=DailyPositionSnapshot.portfolio_id,
                order_by=DailyPositionSnapshot.date.desc()
            ).label('rn')
        ).filter(
            DailyPositionSnapshot.security_id == security_id,
            DailyPositionSnapshot.date < a_date
        ).subquery('ranked_snapshots')

        ranked_alias = aliased(DailyPositionSnapshot, ranked_snapshots_subq)

        stmt = select(ranked_alias).filter(
            ranked_snapshots_subq.c.rn == 1,
            ranked_alias.quantity > 0
        )

        results = await self.db.execute(stmt)
        snapshots = results.scalars().all()
        logger.info(f"Found {len(snapshots)} portfolios holding {security_id} before {a_date} to roll forward.")
        return snapshots

    @async_timed(repository="ValuationRepository", method="upsert_daily_snapshot")
    async def upsert_daily_snapshot(self, snapshot: DailyPositionSnapshot) -> DailyPositionSnapshot:
        """
        Idempotently inserts or updates a daily position snapshot and returns the result.
        """
        try:
            insert_dict = {c.name: getattr(snapshot, c.name) for c in snapshot.__table__.columns if c.name != 'id'}
            
            stmt = pg_insert(DailyPositionSnapshot).values(
                **insert_dict
            ).on_conflict_do_update(
                index_elements=['portfolio_id', 'security_id', 'date'],
                set_={k: v for k, v in insert_dict.items() if k not in ['portfolio_id', 'security_id', 'date']}
            ).returning(DailyPositionSnapshot)

            result = await self.db.execute(stmt)
            persisted_snapshot = result.scalar_one()
            await self.db.flush()
            logger.info(f"Staged upsert for daily snapshot for {snapshot.security_id} on {snapshot.date}")
            return persisted_snapshot
        except Exception as e:
            logger.error(f"Failed to stage upsert for daily snapshot: {e}", exc_info=True)
            raise