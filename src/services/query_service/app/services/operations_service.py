from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.operations_dto import LineageResponse, SupportOverviewResponse
from ..repositories.operations_repository import OperationsRepository


class OperationsService:
    def __init__(self, db: AsyncSession):
        self.repo = OperationsRepository(db)

    async def get_support_overview(self, portfolio_id: str) -> SupportOverviewResponse:
        current_epoch = await self.repo.get_current_portfolio_epoch(portfolio_id)
        active_reprocessing_keys = await self.repo.get_active_reprocessing_keys_count(portfolio_id)
        pending_valuation_jobs = await self.repo.get_pending_valuation_jobs_count(portfolio_id)
        pending_aggregation_jobs = await self.repo.get_pending_aggregation_jobs_count(portfolio_id)
        latest_transaction_date = await self.repo.get_latest_transaction_date(portfolio_id)
        latest_position_snapshot_date = await self.repo.get_latest_snapshot_date_for_current_epoch(
            portfolio_id
        )

        return SupportOverviewResponse(
            portfolio_id=portfolio_id,
            current_epoch=current_epoch,
            active_reprocessing_keys=active_reprocessing_keys,
            pending_valuation_jobs=pending_valuation_jobs,
            pending_aggregation_jobs=pending_aggregation_jobs,
            latest_transaction_date=latest_transaction_date,
            latest_position_snapshot_date=latest_position_snapshot_date,
        )

    async def get_lineage(self, portfolio_id: str, security_id: str) -> LineageResponse:
        position_state = await self.repo.get_position_state(portfolio_id, security_id)
        if not position_state:
            raise ValueError(
                f"Lineage state not found for portfolio '{portfolio_id}' and security '{security_id}'"
            )

        latest_history_date = await self.repo.get_latest_position_history_date(
            portfolio_id, security_id, position_state.epoch
        )
        latest_snapshot_date = await self.repo.get_latest_daily_snapshot_date(
            portfolio_id, security_id, position_state.epoch
        )
        latest_valuation_job = await self.repo.get_latest_valuation_job(
            portfolio_id, security_id, position_state.epoch
        )

        return LineageResponse(
            portfolio_id=portfolio_id,
            security_id=security_id,
            epoch=position_state.epoch,
            watermark_date=position_state.watermark_date,
            reprocessing_status=position_state.status,
            latest_position_history_date=latest_history_date,
            latest_daily_snapshot_date=latest_snapshot_date,
            latest_valuation_job_date=(
                latest_valuation_job.valuation_date if latest_valuation_job else None
            ),
            latest_valuation_job_status=(
                latest_valuation_job.status if latest_valuation_job else None
            ),
        )
