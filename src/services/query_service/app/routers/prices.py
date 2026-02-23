# services/query-service/app/routers/prices.py
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from portfolio_common.db import get_async_db_session
from ..services.price_service import MarketPriceService
from ..dtos.price_dto import MarketPriceResponse

router = APIRouter(prefix="/prices", tags=["Market Prices"])


@router.get("/", response_model=MarketPriceResponse, summary="Get Market Prices for a Security")
async def get_prices(
    security_id: str = Query(..., description="The unique identifier for the security to query."),
    start_date: Optional[date] = Query(
        None, description="The start date for the date range filter (inclusive)."
    ),
    end_date: Optional[date] = Query(
        None, description="The end date for the date range filter (inclusive)."
    ),
    db: AsyncSession = Depends(get_async_db_session),
):
    service = MarketPriceService(db)
    return await service.get_prices(
        security_id=security_id, start_date=start_date, end_date=end_date
    )
