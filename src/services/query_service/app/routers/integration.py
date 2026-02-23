import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from portfolio_common.db import get_async_db_session

from ..dtos.integration_dto import PortfolioCoreSnapshotRequest, PortfolioCoreSnapshotResponse
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
    except Exception:
        logger.exception("Failed to build PAS integration snapshot for portfolio %s", portfolio_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected server error occurred while building integration snapshot.",
        )
