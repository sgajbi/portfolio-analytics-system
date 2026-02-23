# services/query-service/app/routers/fx_rates.py
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from portfolio_common.db import get_async_db_session
from ..services.fx_rate_service import FxRateService
from ..dtos.fx_rate_dto import FxRateResponse

router = APIRouter(prefix="/fx-rates", tags=["FX Rates"])


@router.get(
    "/",
    response_model=FxRateResponse,
    summary="Get FX Rates for a Currency Pair",
    description=(
        "Returns FX rates for a currency pair over an optional date range. "
        "Used by valuation/performance conversion diagnostics and reconciliation."
    ),
)
async def get_fx_rates(
    from_currency: str = Query(
        ..., description="The base currency (e.g., USD).", min_length=3, max_length=3
    ),
    to_currency: str = Query(
        ..., description="The quote currency (e.g., SGD).", min_length=3, max_length=3
    ),
    start_date: Optional[date] = Query(
        None, description="The start date for the date range filter (inclusive)."
    ),
    end_date: Optional[date] = Query(
        None, description="The end date for the date range filter (inclusive)."
    ),
    db: AsyncSession = Depends(get_async_db_session),
):
    service = FxRateService(db)
    return await service.get_fx_rates(
        from_currency=from_currency.upper(),
        to_currency=to_currency.upper(),
        start_date=start_date,
        end_date=end_date,
    )
