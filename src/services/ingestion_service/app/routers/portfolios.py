import logging

from app.ack_response import build_batch_ack
from app.DTOs.ingestion_ack_dto import BatchIngestionAcceptedResponse
from app.DTOs.portfolio_dto import PortfolioIngestionRequest
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
    "/ingest/portfolios",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=BatchIngestionAcceptedResponse,
    tags=["Portfolios"],
    summary="Ingest portfolios",
    description="Accepts canonical portfolios and publishes them for asynchronous processing.",
)
async def ingest_portfolios(
    request: PortfolioIngestionRequest,
    http_request: Request,
    idempotency_key_header: IdempotencyKeyHeader = None,
    ingestion_service: IngestionService = Depends(get_ingestion_service),
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
):
    idempotency_key = idempotency_key_header or resolve_idempotency_key(http_request)
    num_portfolios = len(request.portfolios)
    job_id = create_ingestion_job_id()
    correlation_id, request_id, trace_id = get_request_lineage()
    ingestion_job_service.create_job(
        job_id=job_id,
        endpoint=str(http_request.url.path),
        entity_type="portfolio",
        accepted_count=num_portfolios,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
        request_id=request_id,
        trace_id=trace_id,
    )
    logger.info(
        "Received request to ingest portfolios.",
        extra={"num_portfolios": num_portfolios, "idempotency_key": idempotency_key},
    )

    try:
        await ingestion_service.publish_portfolios(
            request.portfolios, idempotency_key=idempotency_key
        )
        ingestion_job_service.mark_queued(job_id)
    except Exception as exc:
        ingestion_job_service.mark_failed(job_id, str(exc))
        raise

    logger.info("Portfolios successfully queued.", extra={"num_portfolios": num_portfolios})
    return build_batch_ack(
        message="Portfolios accepted for asynchronous ingestion processing.",
        entity_type="portfolio",
        job_id=job_id,
        accepted_count=num_portfolios,
        idempotency_key=idempotency_key,
    )
