import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from portfolio_common.db import get_async_db_session
from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.operations_dto import (
    LineageKeyListResponse,
    LineageResponse,
    SupportJobListResponse,
    SupportOverviewResponse,
)
from ..services.operations_service import OperationsService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Operations Support"])


def get_operations_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> OperationsService:
    return OperationsService(db)


@router.get(
    "/support/portfolios/{portfolio_id}/overview",
    response_model=SupportOverviewResponse,
    responses={status.HTTP_404_NOT_FOUND: {"description": "Portfolio not found."}},
    summary="Get operational support overview for a portfolio",
    description=(
        "Returns support-oriented operational state for a portfolio, including "
        "reprocessing/valuation queue indicators and latest data availability markers."
    ),
)
async def get_support_overview(
    portfolio_id: str, service: OperationsService = Depends(get_operations_service)
):
    try:
        return await service.get_support_overview(portfolio_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception:
        logger.exception("Failed to build support overview for portfolio %s", portfolio_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected server error occurred while building support overview.",
        )


@router.get(
    "/support/portfolios/{portfolio_id}/valuation-jobs",
    response_model=SupportJobListResponse,
    responses={status.HTTP_404_NOT_FOUND: {"description": "Portfolio not found."}},
    summary="List valuation jobs for support workflows",
    description=(
        "Returns valuation jobs for a portfolio with pagination and optional status filtering. "
        "Designed for operations/support dashboards."
    ),
)
async def get_valuation_jobs(
    portfolio_id: str,
    status_filter: Optional[str] = Query(
        None, description="Optional job status filter (e.g., PENDING, PROCESSING)."
    ),
    skip: int = Query(0, ge=0, description="Pagination offset."),
    limit: int = Query(100, ge=1, le=1000, description="Pagination limit."),
    service: OperationsService = Depends(get_operations_service),
):
    try:
        return await service.get_valuation_jobs(
            portfolio_id=portfolio_id, skip=skip, limit=limit, status=status_filter
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception:
        logger.exception("Failed to list valuation jobs for portfolio %s", portfolio_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected server error occurred while listing valuation jobs.",
        )


@router.get(
    "/support/portfolios/{portfolio_id}/aggregation-jobs",
    response_model=SupportJobListResponse,
    responses={status.HTTP_404_NOT_FOUND: {"description": "Portfolio not found."}},
    summary="List aggregation jobs for support workflows",
    description=(
        "Returns aggregation jobs for a portfolio with pagination and optional status filtering. "
        "Designed for operations/support dashboards."
    ),
)
async def get_aggregation_jobs(
    portfolio_id: str,
    status_filter: Optional[str] = Query(
        None, description="Optional job status filter (e.g., PENDING, PROCESSING)."
    ),
    skip: int = Query(0, ge=0, description="Pagination offset."),
    limit: int = Query(100, ge=1, le=1000, description="Pagination limit."),
    service: OperationsService = Depends(get_operations_service),
):
    try:
        return await service.get_aggregation_jobs(
            portfolio_id=portfolio_id, skip=skip, limit=limit, status=status_filter
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception:
        logger.exception("Failed to list aggregation jobs for portfolio %s", portfolio_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected server error occurred while listing aggregation jobs.",
        )


@router.get(
    "/lineage/portfolios/{portfolio_id}/securities/{security_id}",
    response_model=LineageResponse,
    responses={status.HTTP_404_NOT_FOUND: {"description": "Portfolio/security lineage not found."}},
    summary="Get lineage state for a portfolio-security key",
    description=(
        "Returns lineage-relevant state (epoch, watermark, latest artifacts) "
        "for a specific portfolio-security key."
    ),
)
async def get_lineage(
    portfolio_id: str,
    security_id: str,
    service: OperationsService = Depends(get_operations_service),
):
    try:
        return await service.get_lineage(portfolio_id, security_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception:
        logger.exception(
            "Failed to build lineage for portfolio %s security %s", portfolio_id, security_id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected server error occurred while building lineage response.",
        )


@router.get(
    "/lineage/portfolios/{portfolio_id}/keys",
    response_model=LineageKeyListResponse,
    responses={status.HTTP_404_NOT_FOUND: {"description": "Portfolio not found."}},
    summary="List lineage keys for a portfolio",
    description=(
        "Returns current lineage keys (portfolio-security state rows) for a portfolio with "
        "pagination and optional status/security filtering."
    ),
)
async def get_lineage_keys(
    portfolio_id: str,
    reprocessing_status: Optional[str] = Query(
        None, description="Optional status filter for lineage keys (e.g., CURRENT, REPROCESSING)."
    ),
    security_id: Optional[str] = Query(
        None, description="Optional security filter to narrow lineage key results."
    ),
    skip: int = Query(0, ge=0, description="Pagination offset."),
    limit: int = Query(100, ge=1, le=1000, description="Pagination limit."),
    service: OperationsService = Depends(get_operations_service),
):
    try:
        return await service.get_lineage_keys(
            portfolio_id=portfolio_id,
            skip=skip,
            limit=limit,
            reprocessing_status=reprocessing_status,
            security_id=security_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception:
        logger.exception("Failed to list lineage keys for portfolio %s", portfolio_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected server error occurred while listing lineage keys.",
        )

