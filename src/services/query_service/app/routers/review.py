# src/services/query_service/app/routers/review.py
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from portfolio_common.db import get_async_db_session
from ..dtos.review_dto import PortfolioReviewRequest, PortfolioReviewResponse
from ..services.review_service import ReviewService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/portfolios", tags=["Portfolio Review"])


def get_review_service(db: AsyncSession = Depends(get_async_db_session)) -> ReviewService:
    """Dependency injector for the ReviewService."""
    return ReviewService(db)


@router.post(
    "/{portfolio_id}/review",
    response_model=PortfolioReviewResponse,
    response_model_by_alias=True,
    # REMOVED: response_model_exclude_none=True
    summary="Generate a Comprehensive Portfolio Review Report",
)
async def get_portfolio_review(
    portfolio_id: str,
    request: PortfolioReviewRequest,
    review_service: ReviewService = Depends(get_review_service),
):
    """
    Orchestrates and retrieves a consolidated, multi-section report for a portfolio,
    ensuring all data is calculated from a consistent, atomic snapshot of the
    portfolio's active data version.
    """
    try:
        return await review_service.get_portfolio_review(portfolio_id, request)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception:
        logger.exception(
            "An unexpected error occurred during review generation for portfolio %s.", portfolio_id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected server error occurred during review generation.",
        )
