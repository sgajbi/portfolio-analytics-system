# services/query-service/app/routers/positions.py
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from portfolio_common.db import get_async_db_session
from ..services.position_service import PositionService
from ..dtos.position_dto import PortfolioPositionsResponse, PortfolioPositionHistoryResponse

router = APIRouter(prefix="/portfolios", tags=["Positions"])


def get_position_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> PositionService:
    return PositionService(db)


@router.get(
    "/{portfolio_id}/position-history",
    response_model=PortfolioPositionHistoryResponse,
    summary="Get Position History for a Security",
    description=(
        "Returns epoch-aware position history for a portfolio-security key across a date range. "
        "Used for drill-down views and lineage-aware troubleshooting."
    ),
)
async def get_position_history(
    portfolio_id: str,
    security_id: str = Query(..., description="The unique identifier for the security to query."),
    start_date: Optional[date] = Query(
        None, description="The start date for the date range filter (inclusive)."
    ),
    end_date: Optional[date] = Query(
        None, description="The end date for the date range filter (inclusive)."
    ),
    service: PositionService = Depends(get_position_service),
):
    try:
        return await service.get_position_history(
            portfolio_id=portfolio_id,
            security_id=security_id,
            start_date=start_date,
            end_date=end_date,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {e}",
        )


@router.get(
    "/{portfolio_id}/positions",
    response_model=PortfolioPositionsResponse,
    summary="Get Latest Positions for a Portfolio",
    description=(
        "Returns latest current-epoch positions for a portfolio. "
        "Used by holdings screens and downstream review/analytics flows."
    ),
)
async def get_latest_positions(
    portfolio_id: str, service: PositionService = Depends(get_position_service)
):
    try:
        return await service.get_portfolio_positions(portfolio_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {e}",
        )
