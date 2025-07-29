from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session

from portfolio_common.db import get_db_session
from ..services.portfolio_service import PortfolioService
from ..dtos.portfolio_dto import PortfolioQueryResponse

router = APIRouter(
    prefix="/portfolios",
    tags=["Portfolios"]
)

@router.get(
    "/",
    response_model=PortfolioQueryResponse,
    summary="Get Portfolio Details"
)
async def get_portfolios(
    portfolio_id: Optional[str] = Query(None, description="Filter by a single, specific portfolio ID."),
    cif_id: Optional[str] = Query(None, description="Filter by the client grouping ID (CIF) to get all portfolios for a client."),
    booking_center: Optional[str] = Query(None, description="Filter by booking center to get all portfolios for a business unit."),
    db: Session = Depends(get_db_session)
):
    """
    Retrieves a list of portfolios based on optional filter criteria.

    - Provide **portfolio_id** to fetch a single portfolio.
    - Provide **cif_id** to fetch all portfolios for a specific client.
    - Provide **booking_center** to fetch all portfolios for a specific business unit.
    """
    try:
        service = PortfolioService(db)
        return service.get_portfolios(
            portfolio_id=portfolio_id,
            cif_id=cif_id,
            booking_center=booking_center
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {e}"
        )