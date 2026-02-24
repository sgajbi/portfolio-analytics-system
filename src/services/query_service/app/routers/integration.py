import logging
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from portfolio_common.db import get_async_db_session

from ..dtos.integration_dto import (
    EffectiveIntegrationPolicyResponse,
    PortfolioCoreSnapshotRequest,
    PortfolioCoreSnapshotResponse,
    PortfolioPerformanceInputRequest,
    PortfolioPerformanceInputResponse,
)
from ..dtos.review_dto import ReviewSection
from ..services.integration_service import IntegrationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integration", tags=["Integration Contracts"])


def get_integration_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> IntegrationService:
    return IntegrationService(db)


@router.post(
    "/portfolios/{portfolio_id}/core-snapshot",
    response_model=PortfolioCoreSnapshotResponse,
    response_model_by_alias=True,
    summary="Get PAS core snapshot contract for downstream services",
    description=(
        "Returns a versioned PAS snapshot contract for PA/DPM style consumers. "
        "Supports as-of snapshot controls and section-level payload selection."
    ),
)
async def get_portfolio_core_snapshot(
    portfolio_id: str,
    request: PortfolioCoreSnapshotRequest,
    integration_service: IntegrationService = Depends(get_integration_service),
):
    try:
        return await integration_service.get_portfolio_core_snapshot(portfolio_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except Exception:
        logger.exception("Failed to build PAS integration snapshot for portfolio %s", portfolio_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected server error occurred while building integration snapshot.",
        )


@router.get(
    "/policy/effective",
    response_model=EffectiveIntegrationPolicyResponse,
    response_model_by_alias=True,
    summary="Get effective PAS integration snapshot policy",
    description=(
        "Returns effective policy diagnostics and provenance for the given consumer and tenant "
        "context, including strict-mode behavior and allowed sections."
    ),
)
async def get_effective_integration_policy(
    consumer_system: str = Query("BFF", alias="consumerSystem"),
    tenant_id: str = Query("default", alias="tenantId"),
    include_sections: list[ReviewSection] | None = Query(None, alias="includeSections"),
    integration_service: IntegrationService = Depends(get_integration_service),
) -> EffectiveIntegrationPolicyResponse:
    try:
        raw_sections = [section.value for section in include_sections] if include_sections else None
        response = integration_service.get_effective_policy(
            consumer_system=consumer_system,
            tenant_id=tenant_id,
            include_sections=raw_sections,
        )
        return cast(EffectiveIntegrationPolicyResponse, response)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))


@router.post(
    "/portfolios/{portfolio_id}/performance-input",
    response_model=PortfolioPerformanceInputResponse,
    response_model_by_alias=True,
    summary="Get PAS raw performance input series for PA calculation",
    description=(
        "Returns raw portfolio time-series inputs (market values, cashflows, fees) for PA-owned "
        "performance calculation. No PAS performance metric outputs are returned."
    ),
)
async def get_portfolio_performance_input(
    portfolio_id: str,
    request: PortfolioPerformanceInputRequest,
    integration_service: IntegrationService = Depends(get_integration_service),
):
    try:
        return await integration_service.get_portfolio_performance_input(portfolio_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception:
        logger.exception(
            "Failed to build PAS performance input series for portfolio %s", portfolio_id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected server error occurred while building performance input series.",
        )
