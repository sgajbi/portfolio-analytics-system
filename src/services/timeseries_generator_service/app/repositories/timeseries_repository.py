# src/services/timeseries_generator_service/app/repositories/timeseries_repository.py
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional, List
from sqlalchemy import select, text, update, exists, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert
from portfolio_common.database_models import (
    PositionTimeseries, PortfolioTimeseries, Portfolio, Cashflow, FxRate,
    Instrument, PortfolioAggregationJob, MarketPrice, Transaction, DailyPositionSnapshot
)
from portfolio_common.utils import async_timed

logger = logging.getLogger(__name__)

class TimeseriesRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    @async_timed(repository="TimeseriesRepository", method="get_all_snapshots_for_date")
    async def get_all_snapshots_for_date(self, portfolio_id: str, a_date: date) -> List[DailyPositionSnapshot]:
        """Fetches all daily position snapshots for a portfolio on a specific date."""
        stmt = select(DailyPositionSnapshot).filter_by(
            portfolio_id=portfolio_id,
            date=a_date
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

    @async_timed(repository="TimeseriesRepository", method="upsert_position_timeseries")
    async def upsert_position_timeseries(self, timeseries_record: PositionTimeseries):
        try:
            insert_dict = {
                c.name: getattr(timeseries_record, c.name) 
                for c in timeseries_record.__table__.columns
                if c.name not in ['created_at', 'updated_at']
            }
            update_dict = {k: v for k, v in insert_dict.items() if k not in ['portfolio_id', 'security_id', 'date']}
            update_dict['updated_at'] = func.now()
            stmt = pg_insert(PositionTimeseries).values(
                **insert_dict
            ).on_conflict_do_update(
                index_elements=['portfolio_id', 'security_id', 'date'],
                set_=update_dict
            )
            await self.db.execute(stmt)
            logger.info(f"Staged upsert for position time series for {timeseries_record.security_id} on {timeseries_record.date}")
        except Exception as e:
            logger.error(f"Failed to stage upsert for position time series: {e}", exc_info=True)
            raise
    
    @async_timed(repository="TimeseriesRepository", method="upsert_portfolio_timeseries")
    async def upsert_portfolio_timeseries(self, timeseries_record: PortfolioTimeseries):
        try:
            insert_dict = {
                c.name: getattr(timeseries_record, c.name) 
                for c in timeseries_record.__table__.columns
                if c.name not in ['created_at', 'updated_at']
            }
            update_dict = {k: v for k, v in insert_dict.items() if k not in ['portfolio_id', 'date']}
            update_dict['updated_at'] = func.now()
            stmt = pg_insert(PortfolioTimeseries).values(
                **insert_dict
            ).on_conflict_do_update(
                index_elements=['portfolio_id', 'date'],
                set_=update_dict
            )
            await self.db.execute(stmt)
            logger.info(f"Staged upsert for portfolio time series for {timeseries_record.portfolio_id} on {timeseries_record.date}")
        except Exception as e:
            logger.error(f"Failed to stage upsert for portfolio time series: {e}", exc_info=True)
            raise
 
    @async_timed(repository="TimeseriesRepository", method="find_and_claim_eligible_jobs")
    async def find_and_claim_eligible_jobs(self, batch_size: int) -> List[PortfolioAggregationJob]:
        """
        Atomically claims eligible PENDING aggregation jobs. A job for date D is eligible if:
        1. The portfolio timeseries record for date D-1 already exists.
        2. OR this job is for the earliest date for a portfolio that has no timeseries records yet.
        """
        query = text("""
            UPDATE portfolio_aggregation_jobs
            SET status = 'PROCESSING', updated_at = now()
            WHERE id IN (
                SELECT id FROM (
                    SELECT
                        p1.id
                    FROM portfolio_aggregation_jobs p1
                    WHERE p1.status = 'PENDING' AND (
                        -- Case 1: Prior day's timeseries exists, enabling sequential processing.
                        EXISTS (
                            SELECT 1 FROM portfolio_timeseries pts
                            WHERE pts.portfolio_id = p1.portfolio_id
                            AND pts.date = p1.aggregation_date - INTERVAL '1 day'
                        )
                        -- Case 2: This is the very first job for this portfolio.
                        OR p1.aggregation_date = (
                            SELECT MIN(p2.aggregation_date)
                            FROM portfolio_aggregation_jobs p2
                            WHERE p2.portfolio_id = p1.portfolio_id
                            AND NOT EXISTS (
                                SELECT 1 FROM portfolio_timeseries pts
                                WHERE pts.portfolio_id = p1.portfolio_id
                            )
                        )
                    )
                    ORDER BY p1.portfolio_id, p1.aggregation_date
                    LIMIT :batch_size
                    FOR UPDATE SKIP LOCKED
                ) AS eligible_jobs
            )
            RETURNING *;
        """)
        
        result = await self.db.execute(query, {"batch_size": batch_size})
        claimed_jobs = result.mappings().all()
        if claimed_jobs:
            logger.info(f"Found and claimed {len(claimed_jobs)} eligible aggregation jobs.")
        return [PortfolioAggregationJob(**job) for job in claimed_jobs]

    @async_timed(repository="TimeseriesRepository", method="get_portfolio")
    async def get_portfolio(self, portfolio_id: str) -> Optional[Portfolio]:
        result = await self.db.execute(select(Portfolio).filter_by(portfolio_id=portfolio_id))
        return result.scalars().first()

    @async_timed(repository="TimeseriesRepository", method="get_instrument")
    async def get_instrument(self, security_id: str) -> Optional[Instrument]:
        result = await self.db.execute(select(Instrument).filter_by(security_id=security_id))
        return result.scalars().first()

    @async_timed(repository="TimeseriesRepository", method="get_instruments_by_ids")
    async def get_instruments_by_ids(self, security_ids: List[str]) -> List[Instrument]:
        if not security_ids:
            return []
        stmt = select(Instrument).where(Instrument.security_id.in_(security_ids))
        result = await self.db.execute(stmt)
        return result.scalars().all()

    @async_timed(repository="TimeseriesRepository", method="get_fx_rate")
    async def get_fx_rate(self, from_currency: str, to_currency: str, a_date: date) -> Optional[FxRate]:
        stmt = select(FxRate).filter(
            FxRate.from_currency == from_currency,
            FxRate.to_currency == to_currency,
            FxRate.rate_date <= a_date
        ).order_by(FxRate.rate_date.desc())
        result = await self.db.execute(stmt)
        return result.scalars().first()
    
    @async_timed(repository="TimeseriesRepository", method="get_last_position_timeseries_before")
    async def get_last_position_timeseries_before(
        self, portfolio_id: str, security_id: str, a_date: date
    ) -> Optional[PositionTimeseries]:
        stmt = select(PositionTimeseries).filter(
            PositionTimeseries.portfolio_id == portfolio_id,
            PositionTimeseries.security_id == security_id,
            PositionTimeseries.date < a_date
        ).order_by(PositionTimeseries.date.desc())
        result = await self.db.execute(stmt)
        return result.scalars().first()

    @async_timed(repository="TimeseriesRepository", method="get_all_position_timeseries_for_date")
    async def get_all_position_timeseries_for_date(
        self, portfolio_id: str, a_date: date
    ) -> List[PositionTimeseries]:
        stmt = select(PositionTimeseries).filter_by(
            portfolio_id=portfolio_id,
            date=a_date
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

    @async_timed(repository="TimeseriesRepository", method="get_last_portfolio_timeseries_before")
    async def get_last_portfolio_timeseries_before(self, portfolio_id: str, a_date: date) -> Optional[PortfolioTimeseries]:
        stmt = select(PortfolioTimeseries).filter(
            PortfolioTimeseries.portfolio_id == portfolio_id,
            PortfolioTimeseries.date < a_date
        ).order_by(PortfolioTimeseries.date.desc())
        result = await self.db.execute(stmt)
        return result.scalars().first()

    @async_timed(repository="TimeseriesRepository", method="find_and_reset_stale_jobs")
    async def find_and_reset_stale_jobs(self, timeout_minutes: int = 15) -> int:
        stale_threshold = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)
        
        stmt = (
            update(PortfolioAggregationJob)
            .where(
                PortfolioAggregationJob.status == 'PROCESSING',
                PortfolioAggregationJob.updated_at < stale_threshold
            )
            .values(status='PENDING')
        )
        
        result = await self.db.execute(stmt)
        reset_count = result.rowcount
        
        if reset_count > 0:
            logger.warning(f"Reset {reset_count} stale aggregation jobs from 'PROCESSING' to 'PENDING'.")
            
        return reset_count

    @async_timed(repository="TimeseriesRepository", method="get_last_snapshot_before")
    async def get_last_snapshot_before(
        self, portfolio_id: str, security_id: str, a_date: date
    ) -> Optional[DailyPositionSnapshot]:
        stmt = (
            select(DailyPositionSnapshot)
            .filter(
                DailyPositionSnapshot.portfolio_id == portfolio_id,
                DailyPositionSnapshot.security_id == security_id,
                DailyPositionSnapshot.date < a_date,
            )
            .order_by(DailyPositionSnapshot.date.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()