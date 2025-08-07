# services/timeseries-generator-service/app/repositories/timeseries_repository.py
import logging
from datetime import date
from typing import Optional, List
from sqlalchemy import select, text, update, exists
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from portfolio_common.database_models import (
    PositionTimeseries, 
    PortfolioTimeseries, 
    Portfolio, 
    Cashflow, 
    FxRate,
    Instrument,
    PositionHistory,
    PortfolioAggregationJob
)

logger = logging.getLogger(__name__)

class TimeseriesRepository:
    """
    Handles all database read/write operations for time series data.
    """
    def __init__(self, db: AsyncSession):
        self.db = db

    async def find_and_claim_eligible_jobs(self, batch_size: int) -> List[PortfolioAggregationJob]:
        """
        Finds PENDING aggregation jobs where the previous day's job is COMPLETE (or doesn't exist)
        and atomically claims them by updating their status to PROCESSING.
        This is done using a CTE for concurrency-safety, but no longer uses FOR UPDATE SKIP LOCKED
        on the nullable side of a LEFT JOIN (which PostgreSQL does not support).
        """
        query = text("""
            WITH eligible_jobs AS (
                SELECT p1.id
                FROM portfolio_aggregation_jobs p1
                LEFT JOIN portfolio_aggregation_jobs p2
                  ON p1.portfolio_id = p2.portfolio_id
                 AND p2.aggregation_date = p1.aggregation_date - INTERVAL '1 day'
                WHERE p1.status = 'PENDING'
                  AND (p2.status IS NULL OR p2.status = 'COMPLETE')
                ORDER BY p1.portfolio_id, p1.aggregation_date
                LIMIT :batch_size
            )
            UPDATE portfolio_aggregation_jobs
            SET status = 'PROCESSING'
            WHERE id IN (
                SELECT id FROM eligible_jobs
            ) AND status = 'PENDING'
            RETURNING *;
        """)
        
        result = await self.db.execute(query, {"batch_size": batch_size})
        claimed_jobs = result.mappings().all()
        if claimed_jobs:
            logger.info(f"Found and claimed {len(claimed_jobs)} eligible aggregation jobs.")
        return [PortfolioAggregationJob(**job) for job in claimed_jobs]

    async def get_portfolio(self, portfolio_id: str) -> Optional[Portfolio]:
        """Fetches portfolio details by its ID."""
        result = await self.db.execute(select(Portfolio).filter_by(portfolio_id=portfolio_id))
        return result.scalars().first()

    async def get_instrument(self, security_id: str) -> Optional[Instrument]:
        """Fetches an instrument by its security ID."""
        result = await self.db.execute(select(Instrument).filter_by(security_id=security_id))
        return result.scalars().first()
    
    
    async def get_last_portfolio_timeseries_before(self, portfolio_id: str, a_date: date) -> Optional[PortfolioTimeseries]:
        stmt = select(PortfolioTimeseries).filter(
            PortfolioTimeseries.portfolio_id == portfolio_id,
            PortfolioTimeseries.date < a_date
        ).order_by(PortfolioTimeseries.date.desc())
        result = await self.db.execute(stmt)
        return result.scalars().first()
    

    async def get_instruments_by_ids(self, security_ids: List[str]) -> List[Instrument]:
        """Fetches multiple instruments by their security IDs in a single query."""
        if not security_ids:
            return []
        stmt = select(Instrument).where(Instrument.security_id.in_(security_ids))
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_fx_rate(self, from_currency: str, to_currency: str, a_date: date) -> Optional[FxRate]:
        """Fetches the latest FX rate on or before a given date."""
        stmt = select(FxRate).filter(
            FxRate.from_currency == from_currency,
            FxRate.to_currency == to_currency,
            FxRate.rate_date <= a_date
        ).order_by(FxRate.rate_date.desc())
        result = await self.db.execute(stmt)
        return result.scalars().first()

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

    async def is_first_position(self, portfolio_id: str, security_id: str, position_date: date) -> bool:
        """
        Checks if there is any position history for this security prior to the given date.
        Returns True if this is the first known position, False otherwise.
        """
        stmt = select(
            exists().where(
                PositionHistory.portfolio_id == portfolio_id,
                PositionHistory.security_id == security_id,
                PositionHistory.position_date < position_date
            )
        )
        result = await self.db.execute(stmt)
        return not result.scalar()

    async def get_all_position_timeseries_for_date(
        self, portfolio_id: str, a_date: date
    ) -> List[PositionTimeseries]:
        stmt = select(PositionTimeseries).filter_by(
            portfolio_id=portfolio_id,
            date=a_date
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

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

    async def get_portfolio_level_cashflows_for_date(self, portfolio_id: str, a_date: date) -> List[Cashflow]:
        stmt = select(Cashflow).filter_by(
            portfolio_id=portfolio_id,
            cashflow_date=a_date,
            level='PORTFOLIO'
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def upsert_position_timeseries(self, timeseries_record: PositionTimeseries):
        """Idempotent insert/update for a position time series record."""
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
    
    async def upsert_portfolio_timeseries(self, timeseries_record: PortfolioTimeseries):
        """Idempotent insert/update for a portfolio time series record."""
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
