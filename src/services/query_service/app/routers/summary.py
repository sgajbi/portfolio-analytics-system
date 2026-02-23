# src/services/query_service/app/routers/summary.py
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from portfolio_common.db import get_async_db_session
from ..dtos.summary_dto import SummaryRequest, SummaryResponse
from ..services.summary_service import SummaryService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/portfolios", tags=["Portfolio Summary"])


def get_summary_service(db: AsyncSession = Depends(get_async_db_session)) -> SummaryService:
    """Dependency injector for the SummaryService."""
    return SummaryService(db)


@router.post(
    "/{portfolio_id}/summary",
    response_model=SummaryResponse,
    response_model_exclude_none=True,
    summary="Get a Consolidated Portfolio Summary",
)
async def get_portfolio_summary(
    portfolio_id: str,
    request: SummaryRequest,
    summary_service: SummaryService = Depends(get_summary_service),
):
    """
    Retrieves a consolidated, dashboard-style summary for a portfolio.

    This endpoint can calculate various sections in a single call:
    - **Wealth**: Total market value and cash balance.
    - **Allocation**: Breakdowns by asset class, sector, currency, etc.
    """
    try:
        return await summary_service.get_portfolio_summary(portfolio_id, request)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception:
        logger.exception(
            "An unexpected error occurred during summary calculation for portfolio %s.",
            portfolio_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected server error occurred during summary calculation.",
        )
