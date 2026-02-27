import logging

from fastapi import APIRouter, Depends, status

from app.adapter_mode import require_portfolio_bundle_adapter_enabled
from app.DTOs.portfolio_bundle_dto import PortfolioBundleIngestionRequest
from app.services.ingestion_service import IngestionService, get_ingestion_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/ingest/portfolio-bundle",
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        status.HTTP_410_GONE: {
            "description": "Portfolio bundle adapter mode disabled for this environment."
        }
    },
    tags=["Portfolio Bundle"],
    summary="Ingest a complete portfolio bundle",
    description=(
        "Accepts a mixed payload (portfolio, instruments, transactions, market prices, FX rates, "
        "business dates) for UI/manual/file-based onboarding and publishes to existing lotus-core topics."
    ),
)
async def ingest_portfolio_bundle(
    request: PortfolioBundleIngestionRequest,
    _: None = Depends(require_portfolio_bundle_adapter_enabled),
    ingestion_service: IngestionService = Depends(get_ingestion_service),
):
    published_counts = await ingestion_service.publish_portfolio_bundle(request)

    logger.info(
        "Portfolio bundle queued for ingestion.",
        extra={
            "source_system": request.source_system,
            "mode": request.mode,
            "published_counts": published_counts,
        },
    )
    return {
        "message": "Portfolio bundle received and queued for processing.",
        "source_system": request.source_system,
        "mode": request.mode,
        "published_counts": published_counts,
    }
