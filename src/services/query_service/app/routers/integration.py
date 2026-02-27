from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from portfolio_common.db import get_async_db_session

from ..dtos.core_snapshot_dto import CoreSnapshotRequest, CoreSnapshotResponse
from ..dtos.integration_dto import EffectiveIntegrationPolicyResponse
from ..services.core_snapshot_service import (
    CoreSnapshotBadRequestError,
    CoreSnapshotConflictError,
    CoreSnapshotNotFoundError,
    CoreSnapshotService,
    CoreSnapshotUnavailableSectionError,
)
from ..services.integration_service import IntegrationService

router = APIRouter(prefix="/integration", tags=["Integration Contracts"])


def get_integration_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> IntegrationService:
    return IntegrationService(db)


def get_core_snapshot_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> CoreSnapshotService:
    return CoreSnapshotService(db)


@router.get(
    "/policy/effective",
    response_model=EffectiveIntegrationPolicyResponse,
    summary="Get effective lotus-core integration policy",
    description=(
        "Returns effective policy diagnostics and provenance for the given consumer and tenant "
        "context, including strict-mode behavior and allowed sections."
    ),
)
async def get_effective_integration_policy(
    consumer_system: str = Query("lotus-gateway"),
    tenant_id: str = Query("default"),
    include_sections: list[str] | None = Query(None),
    integration_service: IntegrationService = Depends(get_integration_service),
) -> EffectiveIntegrationPolicyResponse:
    response = integration_service.get_effective_policy(
        consumer_system=consumer_system,
        tenant_id=tenant_id,
        include_sections=include_sections,
    )
    return cast(EffectiveIntegrationPolicyResponse, response)


@router.post(
    "/portfolios/{portfolio_id}/core-snapshot",
    response_model=CoreSnapshotResponse,
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "description": "Invalid request payload or invalid section/mode combination."
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Portfolio or simulation session not found."
        },
        status.HTTP_409_CONFLICT: {
            "description": "Simulation expected version mismatch or portfolio/session conflict."
        },
        status.HTTP_422_UNPROCESSABLE_ENTITY: {
            "description": "Section cannot be fulfilled due to missing valuation dependencies."
        },
    },
    summary="Generate a generic core snapshot",
    description=(
        "Returns baseline or simulation snapshot sections for an integration consumer. "
        "Supports positions baseline/projected/delta, portfolio totals, and instrument enrichment."
    ),
)
async def create_core_snapshot(
    portfolio_id: str,
    request: CoreSnapshotRequest,
    service: CoreSnapshotService = Depends(get_core_snapshot_service),
) -> CoreSnapshotResponse:
    try:
        return await service.get_core_snapshot(portfolio_id=portfolio_id, request=request)
    except CoreSnapshotBadRequestError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except CoreSnapshotNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except CoreSnapshotConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except CoreSnapshotUnavailableSectionError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

