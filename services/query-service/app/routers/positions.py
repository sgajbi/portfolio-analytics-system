from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from portfolio_common.db import get_db_session
from ..services.position_service import PositionService
from ..dtos.position_dto import PortfolioPositionsResponse

router = APIRouter(
    prefix="/portfolios",
    tags=["Positions"]
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
        # Basic error handling
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {e}"
        )