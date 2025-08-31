# src/services/query_service/app/routers/positions_analytics.py
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from portfolio_common.db import get_async_db_session
from ..dtos.position_analytics_dto import PositionAnalyticsRequest, PositionAnalyticsResponse
from ..services.position_analytics_service import PositionAnalyticsService, get_position_analytics_service

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/portfolios",
    tags=["Positions"]
)

@router.post(
    "/{portfolio_id}/positions-analytics",
    response_model=PositionAnalyticsResponse,
    response_model_by_alias=True,
    summary="Get On-the-Fly Position-Level Analytics"
)
async def get_position_analytics(
    portfolio_id: str,
    request: PositionAnalyticsRequest,
    service: PositionAnalyticsService = Depends(get_position_analytics_service)
):
    """
    Retrieves a list of all positions for a portfolio and enriches each with
    a configurable set of on-the-fly analytical metrics, such as performance,
    income, and valuation details in both local and base currencies.

    All calculations are performed against the latest **active and complete**
    version of the portfolio's data, ensuring consistency with all other
    system analytics.
    """
    try:
        return await service.get_position_analytics(portfolio_id, request)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception:
        logger.exception(
            "An unexpected error occurred during position analytics generation for portfolio %s.",
            portfolio_id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected server error occurred during position analytics generation."
        )