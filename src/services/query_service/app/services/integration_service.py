from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.integration_dto import PortfolioCoreSnapshotRequest, PortfolioCoreSnapshotResponse
from ..dtos.review_dto import PortfolioReviewRequest
from .portfolio_service import PortfolioService
from .review_service import ReviewService


class IntegrationService:
    """
    Provides PAS integration contracts for downstream services (e.g., PA, DPM).
    """

    def __init__(self, db: AsyncSession):
        self.portfolio_service = PortfolioService(db)
        self.review_service = ReviewService(db)

    async def get_portfolio_core_snapshot(
        self, portfolio_id: str, request: PortfolioCoreSnapshotRequest
    ) -> PortfolioCoreSnapshotResponse:
        portfolio = await self.portfolio_service.get_portfolio_by_id(portfolio_id)

        review_request = PortfolioReviewRequest(
            as_of_date=request.as_of_date, sections=request.include_sections
        )
        snapshot = await self.review_service.get_portfolio_review(portfolio_id, review_request)

        return PortfolioCoreSnapshotResponse(
            consumer_system=request.consumer_system,
            portfolio=portfolio,
            snapshot=snapshot,
        )
