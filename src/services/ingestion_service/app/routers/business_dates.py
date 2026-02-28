# services/ingestion_service/app/routers/business_dates.py
import logging

from app.ack_response import build_batch_ack
from app.DTOs.business_date_dto import BusinessDateIngestionRequest
from app.DTOs.ingestion_ack_dto import BatchIngestionAcceptedResponse
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
    "/ingest/business-dates",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=BatchIngestionAcceptedResponse,
    tags=["Business Dates"],
    summary="Ingest business dates",
    description="Accepts canonical business dates and publishes them for asynchronous processing.",
)
async def ingest_business_dates(
    request: BusinessDateIngestionRequest,
    http_request: Request,
    idempotency_key_header: IdempotencyKeyHeader = None,
    ingestion_service: IngestionService = Depends(get_ingestion_service),
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
):
    idempotency_key = idempotency_key_header or resolve_idempotency_key(http_request)
    num_dates = len(request.business_dates)
    job_id = create_ingestion_job_id()
    correlation_id, request_id, trace_id = get_request_lineage()
    await ingestion_job_service.create_job(
        job_id=job_id,
        endpoint=str(http_request.url.path),
        entity_type="business_date",
        accepted_count=num_dates,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
        request_id=request_id,
        trace_id=trace_id,
    )
    logger.info(
        "Received request to ingest business dates.",
        extra={"num_dates": num_dates, "idempotency_key": idempotency_key},
    )

    try:
        await ingestion_service.publish_business_dates(
            request.business_dates, idempotency_key=idempotency_key
        )
        await ingestion_job_service.mark_queued(job_id)
    except Exception as exc:
        await ingestion_job_service.mark_failed(job_id, str(exc))
        raise

    logger.info("Business dates successfully queued.", extra={"num_dates": num_dates})
    return build_batch_ack(
        message="Business dates accepted for asynchronous ingestion processing.",
        entity_type="business_date",
        job_id=job_id,
        accepted_count=num_dates,
        idempotency_key=idempotency_key,
    )

