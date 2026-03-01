from __future__ import annotations

from typing import NoReturn, cast

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from portfolio_common.db import get_async_db_session

from ..dtos.analytics_input_dto import (
    PortfolioAnalyticsReferenceRequest,
    PortfolioAnalyticsReferenceResponse,
    PortfolioAnalyticsTimeseriesRequest,
    PortfolioAnalyticsTimeseriesResponse,
    PositionAnalyticsTimeseriesRequest,
    PositionAnalyticsTimeseriesResponse,
)
from ..services.analytics_timeseries_service import AnalyticsInputError, AnalyticsTimeseriesService

router = APIRouter(prefix="/integration", tags=["Integration Contracts"])


def get_analytics_timeseries_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> AnalyticsTimeseriesService:
    return AnalyticsTimeseriesService(db)


def _raise_http_for_analytics_error(exc: AnalyticsInputError) -> NoReturn:
    if exc.code == "RESOURCE_NOT_FOUND":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if exc.code == "INVALID_REQUEST":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if exc.code == "INSUFFICIENT_DATA":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    if exc.code == "UNSUPPORTED_CONFIGURATION":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post(
    "/portfolios/{portfolio_id}/analytics/portfolio-timeseries",
    response_model=PortfolioAnalyticsTimeseriesResponse,
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": "Invalid request contract."},
        status.HTTP_404_NOT_FOUND: {"description": "Portfolio not found."},
        status.HTTP_422_UNPROCESSABLE_ENTITY: {
            "description": "Insufficient data or unsupported configuration."
        },
    },
    summary="Fetch portfolio analytics timeseries inputs",
    description=(
        "What: Return canonical portfolio valuation and cash-flow timeseries required by lotus-performance.\n"
        "How: Resolve effective window, apply deterministic paging, and include lineage/quality diagnostics.\n"
        "When: Used for stateful TWR and MWR input acquisition without direct database coupling."
    ),
)
async def get_portfolio_analytics_timeseries(
    portfolio_id: str,
    request: PortfolioAnalyticsTimeseriesRequest,
    service: AnalyticsTimeseriesService = Depends(get_analytics_timeseries_service),
) -> PortfolioAnalyticsTimeseriesResponse:
    try:
        return cast(
            PortfolioAnalyticsTimeseriesResponse,
            await service.get_portfolio_timeseries(portfolio_id=portfolio_id, request=request),
        )
    except AnalyticsInputError as exc:
        _raise_http_for_analytics_error(exc)


@router.post(
    "/portfolios/{portfolio_id}/analytics/position-timeseries",
    response_model=PositionAnalyticsTimeseriesResponse,
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": "Invalid request contract."},
        status.HTTP_404_NOT_FOUND: {"description": "Portfolio not found."},
        status.HTTP_422_UNPROCESSABLE_ENTITY: {
            "description": "Insufficient data or unsupported configuration."
        },
    },
    summary="Fetch position analytics timeseries inputs",
    description=(
        "What: Return canonical position-level valuation timeseries required by contribution and attribution analytics.\n"
        "How: Apply deterministic paging and optional dimension/filter selectors while keeping enrichment separate.\n"
        "When: Used by lotus-performance analytics pipelines for large-window position input retrieval."
    ),
)
async def get_position_analytics_timeseries(
    portfolio_id: str,
    request: PositionAnalyticsTimeseriesRequest,
    service: AnalyticsTimeseriesService = Depends(get_analytics_timeseries_service),
) -> PositionAnalyticsTimeseriesResponse:
    try:
        return cast(
            PositionAnalyticsTimeseriesResponse,
            await service.get_position_timeseries(portfolio_id=portfolio_id, request=request),
        )
    except AnalyticsInputError as exc:
        _raise_http_for_analytics_error(exc)


@router.post(
    "/portfolios/{portfolio_id}/analytics/reference",
    response_model=PortfolioAnalyticsReferenceResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Portfolio not found."},
    },
    summary="Fetch analytics portfolio reference metadata",
    description=(
        "What: Return portfolio-level reference metadata for analytics joins and lifecycle context.\n"
        "How: Resolve canonical portfolio attributes with lineage metadata.\n"
        "When: Used alongside analytics timeseries endpoints to avoid repetitive metadata payload duplication."
    ),
)
async def get_portfolio_analytics_reference(
    portfolio_id: str,
    request: PortfolioAnalyticsReferenceRequest,
    service: AnalyticsTimeseriesService = Depends(get_analytics_timeseries_service),
) -> PortfolioAnalyticsReferenceResponse:
    try:
        return cast(
            PortfolioAnalyticsReferenceResponse,
            await service.get_portfolio_reference(portfolio_id=portfolio_id, request=request),
        )
    except AnalyticsInputError as exc:
        _raise_http_for_analytics_error(exc)
