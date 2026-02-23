from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from portfolio_common.db import get_async_db_session

from ..dtos.lookup_dto import LookupItem, LookupResponse
from ..services.instrument_service import InstrumentService
from ..services.portfolio_service import PortfolioService

router = APIRouter(prefix="/lookups", tags=["Lookup Catalogs"])


async def _fetch_all_instruments(service: InstrumentService, page_limit: int) -> list:
    skip = 0
    collected = []
    while True:
        page = await service.get_instruments(skip=skip, limit=page_limit)
        collected.extend(page.instruments)
        skip += page.limit
        if skip >= page.total:
            break
    return collected


@router.get(
    "/portfolios",
    response_model=LookupResponse,
    summary="Portfolio Lookup Catalog",
    description="Returns portfolio selector options for BFF/UI portfolio selection workflows.",
)
async def get_portfolio_lookups(
    db: AsyncSession = Depends(get_async_db_session),
) -> LookupResponse:
    service = PortfolioService(db)
    response = await service.get_portfolios()

    items = [
        LookupItem(
            id=portfolio.portfolio_id,
            label=portfolio.portfolio_id,
        )
        for portfolio in response.portfolios
    ]
    return LookupResponse(items=items)


@router.get(
    "/instruments",
    response_model=LookupResponse,
    summary="Instrument Lookup Catalog",
    description="Returns instrument selector options for BFF/UI trade and intake workflows.",
)
async def get_instrument_lookups(
    limit: int = Query(default=200, ge=1, le=1000),
    db: AsyncSession = Depends(get_async_db_session),
) -> LookupResponse:
    service = InstrumentService(db)
    response = await service.get_instruments(skip=0, limit=limit)

    items = [
        LookupItem(
            id=instrument.security_id,
            label=f"{instrument.security_id} | {instrument.name}",
        )
        for instrument in response.instruments
    ]
    return LookupResponse(items=items)


@router.get(
    "/currencies",
    response_model=LookupResponse,
    summary="Currency Lookup Catalog",
    description=(
        "Returns distinct currency selector options derived from portfolio base currencies "
        "and instrument currencies."
    ),
)
async def get_currency_lookups(
    instrument_page_limit: int = Query(default=500, ge=50, le=1000),
    db: AsyncSession = Depends(get_async_db_session),
) -> LookupResponse:
    portfolio_service = PortfolioService(db)
    instrument_service = InstrumentService(db)

    portfolios_response = await portfolio_service.get_portfolios()
    instruments = await _fetch_all_instruments(
        service=instrument_service,
        page_limit=instrument_page_limit,
    )

    codes = {
        portfolio.base_currency.upper()
        for portfolio in portfolios_response.portfolios
        if portfolio.base_currency
    }
    codes.update({instrument.currency.upper() for instrument in instruments if instrument.currency})

    items = [LookupItem(id=code, label=code) for code in sorted(codes)]
    return LookupResponse(items=items)
