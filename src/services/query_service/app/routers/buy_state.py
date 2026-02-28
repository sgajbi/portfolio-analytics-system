from fastapi import APIRouter, Depends, HTTPException, status
from portfolio_common.db import get_async_db_session
from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.buy_state_dto import (
    AccruedIncomeOffsetsResponse,
    BuyCashLinkageResponse,
    PositionLotsResponse,
)
from ..services.buy_state_service import BuyStateService

router = APIRouter(prefix="/portfolios", tags=["BUY State"])


def get_buy_state_service(db: AsyncSession = Depends(get_async_db_session)) -> BuyStateService:
    return BuyStateService(db)


@router.get(
    "/{portfolio_id}/positions/{security_id}/lots",
    response_model=PositionLotsResponse,
    summary="Get BUY Lot State for a Position",
    description=(
        "Returns durable BUY lot records for a portfolio-security key, including linkage and "
        "policy metadata used for lifecycle traceability."
    ),
)
async def get_position_lots(
    portfolio_id: str,
    security_id: str,
    service: BuyStateService = Depends(get_buy_state_service),
):
    try:
        return await service.get_position_lots(portfolio_id=portfolio_id, security_id=security_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get(
    "/{portfolio_id}/positions/{security_id}/accrued-offsets",
    response_model=AccruedIncomeOffsetsResponse,
    summary="Get BUY Accrued-Income Offset State",
    description=(
        "Returns accrued-income offset state initialized by BUY events for a portfolio-security key."
    ),
)
async def get_accrued_offsets(
    portfolio_id: str,
    security_id: str,
    service: BuyStateService = Depends(get_buy_state_service),
):
    try:
        return await service.get_accrued_offsets(portfolio_id=portfolio_id, security_id=security_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get(
    "/{portfolio_id}/transactions/{transaction_id}/cash-linkage",
    response_model=BuyCashLinkageResponse,
    summary="Get BUY Cash Linkage State",
    description=(
        "Returns security-side BUY linkage fields and linked cashflow details for reconciliation."
    ),
)
async def get_buy_cash_linkage(
    portfolio_id: str,
    transaction_id: str,
    service: BuyStateService = Depends(get_buy_state_service),
):
    try:
        return await service.get_buy_cash_linkage(
            portfolio_id=portfolio_id, transaction_id=transaction_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
