# services/query-service/app/routers/portfolios.py
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from portfolio_common.db import get_async_db_session
from ..services.portfolio_service import PortfolioService
from ..dtos.portfolio_dto import PortfolioQueryResponse, PortfolioRecord

router = APIRouter(
    prefix="/portfolios",
    tags=["Portfolios"]
)

@router.get("/", response_model=PortfolioQueryResponse, summary="Get Portfolio Details")
async def get_portfolios(
    portfolio_id: Optional[str] = Query(None, description="Filter by a single, specific portfolio ID."),
    cif_id: Optional[str] = Query(None, description="Filter by the client grouping ID (CIF) to get all portfolios for a client."),
    booking_center: Optional[str] = Query(None, description="Filter by booking center to get all portfolios for a business unit."),
    db: AsyncSession = Depends(get_async_db_session)
):
    try:
        service = PortfolioService(db)
        return await service.get_portfolios(
            portfolio_id=portfolio_id,
            cif_id=cif_id,
            booking_center=booking_center
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {e}"
        )

@router.get("/{portfolio_id}", response_model=PortfolioRecord, summary="Get a Single Portfolio by ID")
async def get_portfolio_by_id(
    portfolio_id: str,
    db: AsyncSession = Depends(get_async_db_session)
):
    """
    Retrieves a single portfolio by its unique ID.
    Returns a `404 Not Found` if the portfolio does not exist.
    """
    service = PortfolioService(db)
    try:
        portfolio = await service.get_portfolio_by_id(portfolio_id)
        return portfolio
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Portfolio with id {portfolio_id} not found"
        )