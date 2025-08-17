# src/services/query_service/app/routers/performance.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from portfolio_common.db import get_async_db_session
from ..dtos.performance_dto import PerformanceRequest, PerformanceResponse
from ..services.performance_service import PerformanceService

router = APIRouter(
    prefix="/portfolios",
    tags=["Performance"]
)

@router.post("/{portfolio_id}/performance", response_model=PerformanceResponse)
async def get_performance(
    portfolio_id: str,
    request: PerformanceRequest,
    db: AsyncSession = Depends(get_async_db_session)
):
    """
    Calculates time-weighted return (TWR) for a portfolio over one or more
    specified periods. This is calculated on-the-fly by linking pre-calculated
    daily return factors.
    """
    try:
        service = PerformanceService(db)
        return await service.calculate_performance(portfolio_id, request)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred: {e}")