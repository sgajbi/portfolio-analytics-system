import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from portfolio_common.db import get_async_db_session

from ..dtos.operations_dto import LineageResponse, SupportOverviewResponse
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
    except Exception:
        logger.exception("Failed to build support overview for portfolio %s", portfolio_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected server error occurred while building support overview.",
        )


@router.get(
    "/lineage/portfolios/{portfolio_id}/securities/{security_id}",
    response_model=LineageResponse,
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
