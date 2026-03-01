from fastapi import APIRouter, Depends, HTTPException, status
from portfolio_common.db import get_async_db_session
from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.sell_state_dto import SellCashLinkageResponse, SellDisposalsResponse
from ..services.sell_state_service import SellStateService

router = APIRouter(prefix="/portfolios", tags=["SELL State"])


def get_sell_state_service(db: AsyncSession = Depends(get_async_db_session)) -> SellStateService:
    return SellStateService(db)


@router.get(
    "/{portfolio_id}/positions/{security_id}/sell-disposals",
    response_model=SellDisposalsResponse,
    summary="Get SELL Disposal State for a Position",
    description=(
        "Returns SELL disposal records for a portfolio-security key, including disposed quantity, "
        "disposed cost basis, realized P&L, and policy/linkage metadata for audit and reconciliation."
    ),
)
async def get_sell_disposals(
    portfolio_id: str,
    security_id: str,
    service: SellStateService = Depends(get_sell_state_service),
):
    try:
        return await service.get_sell_disposals(portfolio_id=portfolio_id, security_id=security_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get(
    "/{portfolio_id}/transactions/{transaction_id}/sell-cash-linkage",
    response_model=SellCashLinkageResponse,
    summary="Get SELL Cash Linkage State",
    description=(
        "Returns security-side SELL linkage fields and linked settlement cashflow details "
        "for deterministic reconciliation."
    ),
)
async def get_sell_cash_linkage(
    portfolio_id: str,
    transaction_id: str,
    service: SellStateService = Depends(get_sell_state_service),
):
    try:
        return await service.get_sell_cash_linkage(
            portfolio_id=portfolio_id, transaction_id=transaction_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
