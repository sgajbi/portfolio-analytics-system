# src/services/timeseries_generator_service/app/repositories/timeseries_repository.py
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional, List
from sqlalchemy import select, text, update, exists, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from portfolio_common.database_models import (
    PositionTimeseries,
    PortfolioTimeseries,
    Portfolio,
    Cashflow,
    FxRate,
    Instrument,
    PortfolioAggregationJob,
    MarketPrice,
    Transaction
)
from portfolio_common.utils import async_timed

logger = logging.getLogger(__name__)

class TimeseriesRepository:
    """
    Handles all database read/write operations for time series data.
    """
    def __init__(self, db: AsyncSession):
        self.db = db

    @async_timed(repository="TimeseriesRepository", method="get_portfolio_timeseries_for_date")
    async def get_portfolio_timeseries_for_date(self, portfolio_id: str, a_date: date) -> Optional[PortfolioTimeseries]:
        """Fetches a single portfolio timeseries record for a specific date."""
        stmt = select(PortfolioTimeseries).filter_by(portfolio_id=portfolio_id, date=a_date)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    @async_timed(repository="TimeseriesRepository", method="find_and_claim_eligible_jobs")
    async def find_and_claim_eligible_jobs(self, batch_size: int) -> List[PortfolioAggregationJob]:
        query = text("""
            UPDATE portfolio_aggregation_jobs
            SET status = 'PROCESSING', updated_at = now()
            WHERE id IN (
                SELECT p1.id
                FROM portfolio_aggregation_jobs p1
                WHERE p1.status = 'PENDING'
                AND NOT EXISTS (
                    SELECT 1
                    FROM portfolio_aggregation_jobs p2
                    WHERE p2.portfolio_id = p1.portfolio_id
                    AND p2.aggregation_date = p1.aggregation_date - INTERVAL '1 day'
                    AND p2.status != 'COMPLETE'
                )
                ORDER BY p1.portfolio_id, p1.aggregation_date
                LIMIT :batch_size
                FOR UPDATE SKIP LOCKED
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
    
    @async_timed(repository="TimeseriesRepository", method="get_latest_price_for_position")
    async def get_latest_price_for_position(self, security_id: str, position_date: date) -> Optional[MarketPrice]:
        stmt = select(MarketPrice).filter(
            MarketPrice.security_id == security_id,
            MarketPrice.price_date <= position_date
        ).order_by(MarketPrice.price_date.desc())
        result = await self.db.execute(stmt)
        return result.scalars().first()

    @async_timed(repository="TimeseriesRepository", method="get_last_position_timeseries_before")
    async def get_last_position_timeseries_before(
        self,
        portfolio_id: str,
        security_id: str,
        a_date: date
    ) -> Optional[PositionTimeseries]:
        stmt = select(PositionTimeseries).filter(
            PositionTimeseries.portfolio_id == portfolio_id,
            PositionTimeseries.security_id == security_id,
            PositionTimeseries.date < a_date
        ).order_by(PositionTimeseries.date.desc())
        result = await self.db.execute(stmt)
        return result.scalars().first()

    @async_timed(repository="TimeseriesRepository", method="is_first_position")
    async def is_first_position(self, portfolio_id: str, security_id: str, position_date: date) -> bool:
        stmt = select(
            exists().where(
                Transaction.portfolio_id == portfolio_id,
                Transaction.security_id == security_id,
                func.date(Transaction.transaction_date) < position_date,
                Transaction.transaction_type.in_(['BUY', 'SELL'])
            )
        )
        result = await self.db.execute(stmt)
        return not result.scalar()

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

    @async_timed(repository="TimeseriesRepository", method="get_all_cashflows_for_security_date")
    async def get_all_cashflows_for_security_date(
        self, portfolio_id: str, security_id: str, a_date: date
    ) -> List[Cashflow]:
        stmt = select(Cashflow).filter_by(
            portfolio_id=portfolio_id,
            security_id=security_id,
            cashflow_date=a_date
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

    @async_timed(repository="TimeseriesRepository", method="get_portfolio_level_cashflows_for_date")
    async def get_portfolio_level_cashflows_for_date(self, portfolio_id: str, a_date: date) -> List[Cashflow]:
        stmt = select(Cashflow).filter_by(
            portfolio_id=portfolio_id,
            cashflow_date=a_date,
            level='PORTFOLIO'
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

    @async_timed(repository="TimeseriesRepository", method="upsert_position_timeseries")
    async def upsert_position_timeseries(self, timeseries_record: PositionTimeseries):
        try:
            insert_dict = {c.name: getattr(timeseries_record, c.name) for c in timeseries_record.__table__.columns}
            update_dict = {k: v for k, v in insert_dict.items() if k not in ['portfolio_id', 'security_id', 'date']}
            
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
            insert_dict = {c.name: getattr(timeseries_record, c.name) for c in timeseries_record.__table__.columns}
            update_dict = {k: v for k, v in insert_dict.items() if k not in ['portfolio_id', 'date']}

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

    @async_timed(repository="TimeseriesRepository", method="get_last_portfolio_timeseries_before")
    async def get_last_portfolio_timeseries_before(self, portfolio_id: str, a_date: date) -> Optional[PortfolioTimeseries]:
        stmt = select(PortfolioTimeseries).filter(
            PortfolioTimeseries.portfolio_id == portfolio_id,
            PortfolioTimeseries.date < a_date
        ).order_by(PortfolioTimeseries.date.desc())
        result = await self.db.execute(stmt)
        return result.scalars().first()

    @async_timed(repository="TimeseriesRepository", method="get_all_open_positions_as_of")
    async def get_all_open_positions_as_of(self, portfolio_id: str, a_date: date) -> List[str]:
        stmt = text("""
            SELECT DISTINCT security_id
            FROM position_timeseries
            WHERE portfolio_id = :portfolio_id
            AND date <= :a_date
            AND quantity != 0
            ORDER BY security_id
        """)
        result = await self.db.execute(stmt, {"portfolio_id": portfolio_id, "a_date": a_date})
        return [row.security_id for row in result.fetchall()]

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