from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from portfolio_common.db import get_db_session
from ..services.position_service import PositionService
from ..dtos.position_dto import PortfolioPositionsResponse, PortfolioPositionHistoryResponse

router = APIRouter(
    prefix="/portfolios",
    tags=["Positions"]
)

@router.get(
    "/{portfolio_id}/position-history",
    response_model=PortfolioPositionHistoryResponse,
    summary="Get Position History for a Security"
)
async def get_position_history(
    portfolio_id: str,
    security_id: str = Query(..., description="The unique identifier for the security to query."),
    start_date: Optional[date] = Query(None, description="The start date for the date range filter (inclusive)."),
    end_date: Optional[date] = Query(None, description="The end date for the date range filter (inclusive)."),
    db: Session = Depends(get_db_session)
):
    """
    Retrieves the time-series position history for a **single security**
    within a specific portfolio, with an optional date range filter.
    """
    try:
        service = PositionService(db)
        return service.get_position_history(
            portfolio_id=portfolio_id,
            security_id=security_id,
            start_date=start_date,
            end_date=end_date
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {e}"
        )

@router.get(
    "/{portfolio_id}/positions",
    response_model=PortfolioPositionsResponse,
    summary="Get Latest Positions for a Portfolio"
)
async def get_latest_positions(portfolio_id: str, db: Session = Depends(get_db_session)):
    """
    Retrieves the latest position for each security held in a specific portfolio.
    Positions with a quantity of zero are excluded.
    """
    try:
        service = PositionService(db)
        return service.get_portfolio_positions(portfolio_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {e}"
        )