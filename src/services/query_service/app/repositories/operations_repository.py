from datetime import date
from typing import Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from portfolio_common.database_models import (
    DailyPositionSnapshot,
    PortfolioAggregationJob,
    PortfolioValuationJob,
    PositionHistory,
    PositionState,
    Transaction,
)


class OperationsRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_current_portfolio_epoch(self, portfolio_id: str) -> Optional[int]:
        stmt = select(func.max(PositionState.epoch)).where(
            PositionState.portfolio_id == portfolio_id
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_active_reprocessing_keys_count(self, portfolio_id: str) -> int:
        stmt = (
            select(func.count())
            .select_from(PositionState)
            .where(
                PositionState.portfolio_id == portfolio_id,
                PositionState.status == "REPROCESSING",
            )
        )
        return int((await self.db.execute(stmt)).scalar_one() or 0)

    async def get_pending_valuation_jobs_count(self, portfolio_id: str) -> int:
        stmt = (
            select(func.count())
            .select_from(PortfolioValuationJob)
            .where(
                PortfolioValuationJob.portfolio_id == portfolio_id,
                PortfolioValuationJob.status.in_(("PENDING", "PROCESSING")),
            )
        )
        return int((await self.db.execute(stmt)).scalar_one() or 0)

    async def get_pending_aggregation_jobs_count(self, portfolio_id: str) -> int:
        stmt = (
            select(func.count())
            .select_from(PortfolioAggregationJob)
            .where(
                PortfolioAggregationJob.portfolio_id == portfolio_id,
                PortfolioAggregationJob.status.in_(("PENDING", "PROCESSING")),
            )
        )
        return int((await self.db.execute(stmt)).scalar_one() or 0)

    async def get_latest_transaction_date(self, portfolio_id: str) -> Optional[date]:
        stmt = select(func.max(func.date(Transaction.transaction_date))).where(
            Transaction.portfolio_id == portfolio_id
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_latest_snapshot_date_for_current_epoch(self, portfolio_id: str) -> Optional[date]:
        stmt = (
            select(func.max(DailyPositionSnapshot.date))
            .join(
                PositionState,
                and_(
                    DailyPositionSnapshot.portfolio_id == PositionState.portfolio_id,
                    DailyPositionSnapshot.security_id == PositionState.security_id,
                    DailyPositionSnapshot.epoch == PositionState.epoch,
                ),
            )
            .where(DailyPositionSnapshot.portfolio_id == portfolio_id)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_position_state(
        self, portfolio_id: str, security_id: str
    ) -> Optional[PositionState]:
        stmt = select(PositionState).where(
            PositionState.portfolio_id == portfolio_id,
            PositionState.security_id == security_id,
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_latest_position_history_date(
        self, portfolio_id: str, security_id: str, epoch: int
    ) -> Optional[date]:
        stmt = select(func.max(PositionHistory.position_date)).where(
            PositionHistory.portfolio_id == portfolio_id,
            PositionHistory.security_id == security_id,
            PositionHistory.epoch == epoch,
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_latest_daily_snapshot_date(
        self, portfolio_id: str, security_id: str, epoch: int
    ) -> Optional[date]:
        stmt = select(func.max(DailyPositionSnapshot.date)).where(
            DailyPositionSnapshot.portfolio_id == portfolio_id,
            DailyPositionSnapshot.security_id == security_id,
            DailyPositionSnapshot.epoch == epoch,
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_latest_valuation_job(
        self, portfolio_id: str, security_id: str, epoch: int
    ) -> Optional[PortfolioValuationJob]:
        stmt = (
            select(PortfolioValuationJob)
            .where(
                PortfolioValuationJob.portfolio_id == portfolio_id,
                PortfolioValuationJob.security_id == security_id,
                PortfolioValuationJob.epoch == epoch,
            )
            .order_by(PortfolioValuationJob.valuation_date.desc(), PortfolioValuationJob.id.desc())
            .limit(1)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()
