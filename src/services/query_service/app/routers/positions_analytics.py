# src/services/query_service/app/routers/positions_analytics.py
import logging
from fastapi import APIRouter, Depends, HTTPException, status

from ..services.position_analytics_service import (
    PositionAnalyticsService,
    get_position_analytics_service,
)
from ..dtos.position_analytics_dto import PositionAnalyticsRequest, PositionAnalyticsResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/portfolios", tags=["Position Analytics"])


@router.post(
    "/{portfolio_id}/positions-analytics",
    response_model=PositionAnalyticsResponse,
    response_model_exclude_none=True,
    responses={status.HTTP_404_NOT_FOUND: {"description": "Portfolio not found."}},
    summary="Retrieve Detailed Position-Level Analytics",
    description=(
        "Provides a detailed, multi-section breakdown of analytics for all "
        "positions held within a portfolio as of a specific date."
    ),
)
async def get_position_analytics(
    portfolio_id: str,
    request: PositionAnalyticsRequest,
    service: PositionAnalyticsService = Depends(get_position_analytics_service),
):
    """
    Retrieves comprehensive position-level analytics.

    - **portfolio_id**: The unique identifier for the portfolio.
    - **Request Body**: A JSON object specifying the as-of date and the sections
      of analytics to be included (e.g., valuation, performance, instrument details).
    """
    try:
        return await service.get_position_analytics(portfolio_id, request)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception:
        logger.exception(
            "An unexpected error occurred during position analytics retrieval for portfolio %s.",
            portfolio_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected server error occurred.",
        )
