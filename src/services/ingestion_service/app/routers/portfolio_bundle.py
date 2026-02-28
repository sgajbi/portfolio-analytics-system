import logging

from app.ack_response import build_batch_ack
from app.adapter_mode import require_portfolio_bundle_adapter_enabled
from app.DTOs.ingestion_ack_dto import BatchIngestionAcceptedResponse
from app.DTOs.portfolio_bundle_dto import PortfolioBundleIngestionRequest
from app.request_metadata import (
    IdempotencyKeyHeader,
    create_ingestion_job_id,
    get_request_lineage,
    resolve_idempotency_key,
)
from app.services.ingestion_job_service import IngestionJobService, get_ingestion_job_service
from app.services.ingestion_service import IngestionService, get_ingestion_service
from fastapi import APIRouter, Depends, Request, status

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/ingest/portfolio-bundle",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=BatchIngestionAcceptedResponse,
    responses={
        status.HTTP_410_GONE: {
            "description": "Portfolio bundle adapter mode disabled for this environment."
        }
    },
    tags=["Portfolio Bundle"],
    summary="Ingest a complete portfolio bundle",
    description=(
        "Accepts a mixed payload (portfolio, instruments, transactions, market prices, FX rates, "
        "business dates) for UI/manual/file-based onboarding and publishes to "
        "existing lotus-core topics."
    ),
)
async def ingest_portfolio_bundle(
    request: PortfolioBundleIngestionRequest,
    http_request: Request,
    idempotency_key_header: IdempotencyKeyHeader = None,
    _: None = Depends(require_portfolio_bundle_adapter_enabled),
    ingestion_service: IngestionService = Depends(get_ingestion_service),
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
):
    idempotency_key = idempotency_key_header or resolve_idempotency_key(http_request)
    accepted_count = (
        len(request.business_dates)
        + len(request.portfolios)
        + len(request.instruments)
        + len(request.transactions)
        + len(request.market_prices)
        + len(request.fx_rates)
    )
    job_id = create_ingestion_job_id()
    correlation_id, request_id, trace_id = get_request_lineage()
    ingestion_job_service.create_job(
        job_id=job_id,
        endpoint=str(http_request.url.path),
        entity_type="portfolio_bundle",
        accepted_count=accepted_count,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
        request_id=request_id,
        trace_id=trace_id,
    )
    try:
        published_counts = await ingestion_service.publish_portfolio_bundle(
            request, idempotency_key=idempotency_key
        )
        ingestion_job_service.mark_queued(job_id)
    except Exception as exc:
        ingestion_job_service.mark_failed(job_id, str(exc))
        raise

    logger.info(
        "Portfolio bundle queued for ingestion.",
        extra={
            "source_system": request.source_system,
            "mode": request.mode,
            "published_counts": published_counts,
            "idempotency_key": idempotency_key,
        },
    )
    return build_batch_ack(
        message=(
            "Portfolio bundle accepted for asynchronous ingestion processing. "
            f"Published counts: {published_counts}"
        ),
        entity_type="portfolio_bundle",
        job_id=job_id,
        accepted_count=accepted_count,
        idempotency_key=idempotency_key,
    )
