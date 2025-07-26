from datetime import date
from typing import Optional, Dict
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from portfolio_common.db import get_db_session
from ..services.transaction_service import TransactionService
from ..dtos.transaction_dto import PaginatedTransactionResponse
from ..dependencies import pagination_params

router = APIRouter(
    prefix="/portfolios",
    tags=["Transactions"]
)

@router.get(
    "/{portfolio_id}/transactions",
    response_model=PaginatedTransactionResponse,
    summary="Get Transactions for a Portfolio"
)
async def get_transactions(
    portfolio_id: str,
    security_id: Optional[str] = Query(None, description="Filter by a specific security ID."),
    start_date: Optional[date] = Query(None, description="The start date for the date range filter (inclusive)."),
    end_date: Optional[date] = Query(None, description="The end date for the date range filter (inclusive)."),
    pagination: Dict[str, int] = Depends(pagination_params),
    db: Session = Depends(get_db_session)
):
    """
    Retrieves a paginated list of transactions for a specific portfolio,
    with optional filters for security and date range.
    """
    service = TransactionService(db)
    return service.get_transactions(
        portfolio_id=portfolio_id,
        security_id=security_id,
        start_date=start_date,
        end_date=end_date,
        **pagination
    )