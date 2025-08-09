# services/query-service/app/routers/instruments.py
from typing import Optional, Dict
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from portfolio_common.db import get_async_db_session
from ..services.instrument_service import InstrumentService
from ..dtos.instrument_dto import PaginatedInstrumentResponse
from ..dependencies import pagination_params

router = APIRouter(
    prefix="/instruments",
    tags=["Instruments"]
)

@router.get("/", response_model=PaginatedInstrumentResponse, summary="Get a List of Instruments")
async def get_instruments(
    security_id: Optional[str] = Query(None, description="Filter by a specific security ID."),
    product_type: Optional[str] = Query(None, description="Filter by a specific product type (e.g., Equity)."),
    pagination: Dict[str, int] = Depends(pagination_params),
    db: AsyncSession = Depends(get_async_db_session)
):
    service = InstrumentService(db)
    return await service.get_instruments(
        security_id=security_id,
        product_type=product_type,
        **pagination
    )