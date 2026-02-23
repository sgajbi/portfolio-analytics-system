# services/query-service/app/routers/transactions.py
from datetime import date
from typing import Optional, Dict
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from portfolio_common.db import get_async_db_session
from ..services.transaction_service import TransactionService
from ..dtos.transaction_dto import PaginatedTransactionResponse
from ..dependencies import pagination_params, sorting_params  # <-- IMPORT NEW DEPENDENCY

router = APIRouter(prefix="/portfolios", tags=["Transactions"])


@router.get(
    "/{portfolio_id}/transactions",
    response_model=PaginatedTransactionResponse,
    summary="Get Transactions for a Portfolio",
    description=(
        "Returns transactions for a portfolio with filters, pagination, and sorting. "
        "Designed for transaction ledgers, audit timelines, and investigative support."
    ),
)
async def get_transactions(
    portfolio_id: str,
    security_id: Optional[str] = Query(None, description="Filter by a specific security ID."),
    start_date: Optional[date] = Query(
        None, description="The start date for the date range filter (inclusive)."
    ),
    end_date: Optional[date] = Query(
        None, description="The end date for the date range filter (inclusive)."
    ),
    pagination: Dict[str, int] = Depends(pagination_params),
    sorting: Dict[str, Optional[str]] = Depends(sorting_params),  # <-- USE NEW DEPENDENCY
    db: AsyncSession = Depends(get_async_db_session),
):
    service = TransactionService(db)
    return await service.get_transactions(
        portfolio_id=portfolio_id,
        security_id=security_id,
        start_date=start_date,
        end_date=end_date,
        **pagination,
        **sorting,
    )
