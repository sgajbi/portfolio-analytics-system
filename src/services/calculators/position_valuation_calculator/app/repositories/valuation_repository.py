# services/calculators/position-valuation-calculator/app/repositories/valuation_repository.py
import logging
from datetime import date
from typing import List, Optional
from sqlalchemy import select, func, distinct, exists, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import aliased

from portfolio_common.database_models import (
    PositionHistory, MarketPrice, DailyPositionSnapshot, FxRate, Instrument, Portfolio,
    PortfolioValuationJob
)
from portfolio_common.utils import async_timed

logger = logging.getLogger(__name__)

class ValuationRepository:
    """
    Handles all database interactions for the position valuation service.
    """
    def __init__(self, db: AsyncSession):
        self.db = db

    @async_timed(repository="ValuationRepository", method="update_job_status")
    async def update_job_status(self, portfolio_id: str, security_id: str, valuation_date: date, status: str):
        """Updates the status of a specific valuation job."""
        stmt = (
            update(PortfolioValuationJob)
            .where(
                PortfolioValuationJob.portfolio_id == portfolio_id,
                PortfolioValuationJob.security_id == security_id,
                PortfolioValuationJob.valuation_date == valuation_date
            )
            .values(status=status, updated_at=func.now())
        )
        await self.db.execute(stmt)

    @async_timed(repository="ValuationRepository", method="find_and_claim_eligible_jobs")
    async def find_and_claim_eligible_jobs(self, batch_size: int) -> List[PortfolioValuationJob]:
        """
        Finds PENDING valuation jobs, atomically claims them by updating their
        status to PROCESSING, and returns the claimed jobs.
        """
        query = text("""
            UPDATE portfolio_valuation_jobs
            SET status = 'PROCESSING'
            WHERE id IN (
                SELECT id
                FROM portfolio_valuation_jobs
                WHERE status = 'PENDING'
                ORDER BY portfolio_id, security_id, valuation_date
                LIMIT :batch_size
                FOR UPDATE SKIP LOCKED
            )
            RETURNING *;
        """)
        
        result = await self.db.execute(query, {"batch_size": batch_size})
        claimed_jobs = result.mappings().all()
        if claimed_jobs:
            logger.info(f"Found and claimed {len(claimed_jobs)} eligible valuation jobs.")
        return [PortfolioValuationJob(**job) for job in claimed_jobs]

    @async_timed(repository="ValuationRepository", method="get_daily_snapshot")
    async def get_daily_snapshot(self, portfolio_id: str, security_id: str, a_date: date) -> Optional[DailyPositionSnapshot]:
        """Fetches a single daily position snapshot for a specific key."""
        stmt = select(DailyPositionSnapshot).filter_by(
            portfolio_id=portfolio_id,
            security_id=security_id,
            date=a_date
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()

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

    @async_timed(repository="ValuationRepository", method="find_and_reset_stale_jobs")
    async def find_and_reset_stale_jobs(self, timeout_minutes: int = 15) -> int:
        """
        Finds jobs stuck in 'PROCESSING' state for longer than the timeout
        and resets them to 'PENDING'. This is a recovery mechanism for crashed workers.
        """
        stale_threshold = func.now() - func.text(f"INTERVAL '{timeout_minutes} minutes'")
        
        stmt = (
            update(PortfolioValuationJob)
            .where(
                PortfolioValuationJob.status == 'PROCESSING',
                PortfolioValuationJob.updated_at < stale_threshold
            )
            .values(status='PENDING')
        )
        
        result = await self.db.execute(stmt)
        reset_count = result.rowcount
        
        if reset_count > 0:
            logger.warning(f"Reset {reset_count} stale valuation jobs from 'PROCESSING' to 'PENDING'.")
            
        return reset_count