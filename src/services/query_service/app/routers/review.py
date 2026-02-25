# src/services/query_service/app/routers/review.py
from fastapi import APIRouter
from ..dtos.review_dto import PortfolioReviewRequest, PortfolioReviewResponse
from .legacy_gone import raise_legacy_endpoint_gone

router = APIRouter(prefix="/portfolios", tags=["Portfolio Review"])


@router.post(
    "/{portfolio_id}/review",
    response_model=PortfolioReviewResponse,
    response_model_by_alias=True,
    deprecated=True,
    summary="Generate a Comprehensive Portfolio Review Report (Deprecated: moved to RAS)",
)
async def get_portfolio_review(
    portfolio_id: str,
    request: PortfolioReviewRequest,
):
    """
    Deprecated: reporting endpoint ownership has moved to RAS.
    Use `reporting-aggregation-service` endpoint:
    `POST /reports/portfolios/{portfolio_id}/review`.

    Orchestrates and retrieves a consolidated, multi-section report for a portfolio,
    ensuring all data is calculated from a consistent, atomic snapshot of the
    portfolio's active data version.
    """
    _ = (portfolio_id, request)
    raise_legacy_endpoint_gone(
        capability="portfolio_review_report",
        target_service="RAS",
        target_endpoint="/reports/portfolios/{portfolio_id}/review",
    )
