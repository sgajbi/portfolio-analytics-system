# services/query-service/app/routers/transactions.py
from datetime import date
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from portfolio_common.db import get_async_db_session
from sqlalchemy.ext.asyncio import AsyncSession

from ..dependencies import pagination_params, sorting_params
from ..dtos.transaction_dto import PaginatedTransactionResponse
from ..services.transaction_service import TransactionService

router = APIRouter(prefix="/portfolios", tags=["Transactions"])


@router.get(
    "/{portfolio_id}/transactions",
    response_model=PaginatedTransactionResponse,
    responses={status.HTTP_404_NOT_FOUND: {"description": "Portfolio not found."}},
    summary="Get Transactions for a Portfolio",
    description=(
        "Returns transactions for a portfolio with filters, pagination, and sorting. "
        "Designed for transaction ledgers, audit timelines, and investigative support."
    ),
)
async def get_transactions(
    portfolio_id: str = Path(..., description="Portfolio identifier."),
    security_id: Optional[str] = Query(None, description="Filter by a specific security ID."),
    start_date: Optional[date] = Query(
        None, description="The start date for the date range filter (inclusive)."
    ),
    end_date: Optional[date] = Query(
        None, description="The end date for the date range filter (inclusive)."
    ),
    as_of_date: Optional[date] = Query(
        None,
        description=(
            "Optional as-of date for booked transaction state. "
            "If omitted and include_projected is false, latest business_date is used."
        ),
    ),
    include_projected: bool = Query(
        False,
        description=(
            "When true, includes future-dated projected transactions "
            "beyond current business_date."
        ),
    ),
    pagination: Dict[str, int] = Depends(pagination_params),
    sorting: Dict[str, Optional[str]] = Depends(sorting_params),
    db: AsyncSession = Depends(get_async_db_session),
):
    service = TransactionService(db)
    try:
        return await service.get_transactions(
            portfolio_id=portfolio_id,
            security_id=security_id,
            start_date=start_date,
            end_date=end_date,
            as_of_date=as_of_date,
            include_projected=include_projected,
            **pagination,
            **sorting,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
