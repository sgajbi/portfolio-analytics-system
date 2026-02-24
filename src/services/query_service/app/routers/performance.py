# src/services/query_service/app/routers/performance.py
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from portfolio_common.db import get_async_db_session
from ..dtos.performance_dto import PerformanceRequest, PerformanceResponse
from ..services.performance_service import PerformanceService
from ..dtos.mwr_dto import MWRRequest, MWRResponse
from ..services.mwr_service import MWRService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/portfolios", tags=["Performance"])


@router.post(
    "/{portfolio_id}/performance",
    response_model=PerformanceResponse,
    response_model_exclude_none=True,
    summary="[Deprecated] Calculate On-the-Fly Portfolio Performance (TWR)",
    description=(
        "Deprecated: advanced performance analytics ownership has moved to PA. "
        "Use PA APIs for authoritative performance calculations."
    ),
    deprecated=True,
)
async def calculate_performance(
    portfolio_id: str, request: PerformanceRequest, db: AsyncSession = Depends(get_async_db_session)
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
    except Exception:
        # Catch-all for any unexpected errors during calculation
        logger.exception("An unexpected error occurred during performance calculation.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected server error occurred.",
        )


@router.post(
    "/{portfolio_id}/performance/mwr",
    response_model=MWRResponse,
    summary="[Deprecated] Calculate Money-Weighted Return (MWR / IRR) for a Portfolio",
    description=(
        "Deprecated: advanced performance analytics ownership has moved to PA. "
        "Use PA APIs for authoritative MWR calculations."
    ),
    deprecated=True,
)
async def calculate_mwr(
    portfolio_id: str, request: MWRRequest, db: AsyncSession = Depends(get_async_db_session)
):
    """
    Calculates money-weighted return (MWR/IRR) for a portfolio over one or more
    specified periods.

    - **portfolio_id**: The unique identifier for the portfolio.
    - **Request Body**: A JSON object specifying the scope and periods for the MWR calculation.
    """
    try:
        service = MWRService(db)
        return await service.calculate_mwr(portfolio_id, request)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception:
        logger.exception("An unexpected error occurred during MWR calculation.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected server error occurred.",
        )
