# src/services/query_service/app/routers/performance.py
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from portfolio_common.db import get_async_db_session
from ..dtos.performance_dto import PerformanceRequest, PerformanceResponse
from ..services.performance_service import PerformanceService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/portfolios",
    tags=["Performance"]
)

@router.post(
  
    "/{portfolio_id}/performance",
    response_model=PerformanceResponse,
    response_model_exclude_none=True,
    summary="Calculate On-the-Fly Portfolio Performance",
    description="Calculates time-weighted return (TWR) for a portfolio over one or more specified periods, with support for various period types, breakdowns, and currency conversion."
)
async def calculate_performance(
    portfolio_id: str,
    request: PerformanceRequest,
    db: AsyncSession = Depends(get_async_db_session)
):
    """
    Calculates portfolio performance based on a flexible request.

    - **portfolio_id**: The unique identifier for the portfolio.
    - **Request Body**: A JSON object specifying the scope, periods, and options for the calculation.
    """
    try:
        service = PerformanceService(db)
        # The service will handle the logic using the portfolio_id from the path
        # and the detailed request from the body.
        return await service.calculate_performance(portfolio_id, request)
    except ValueError as e:
        # Catches cases like "Portfolio not found"
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        # Catch-all for any unexpected errors during calculation
        logger.exception("An unexpected error occurred during performance calculation.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected server error occurred."
        )