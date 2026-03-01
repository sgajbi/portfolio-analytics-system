# services/ingestion_service/app/routers/business_dates.py
import logging

from app.ack_response import build_batch_ack
from app.DTOs.business_date_dto import BusinessDateIngestionRequest
from app.DTOs.ingestion_ack_dto import BatchIngestionAcceptedResponse
from app.ops_controls import enforce_ingestion_write_rate_limit
from app.request_metadata import (    create_ingestion_job_id,
    get_request_lineage,
    resolve_idempotency_key,
)
from app.services.ingestion_job_service import IngestionJobService, get_ingestion_job_service
from app.services.ingestion_service import (
    IngestionPublishError,
    IngestionService,
    get_ingestion_service,
)
from fastapi import APIRouter, Depends, HTTPException, Request, status

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/ingest/business-dates",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=BatchIngestionAcceptedResponse,
    tags=["Business Dates"],
    summary="Ingest business dates",
    description=(
        "What: Accept canonical business calendar dates used by valuation and processing lifecycles.\n"
        "How: Validate date records, apply ingestion controls, and publish asynchronous persistence events.\n"
        "When: Use for calendar setup, holiday updates, and date-correction operations."
    ),
)
async def ingest_business_dates(
    request: BusinessDateIngestionRequest,
    http_request: Request,    ingestion_service: IngestionService = Depends(get_ingestion_service),
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
):
    idempotency_key = resolve_idempotency_key(http_request)
    try:
        await ingestion_job_service.assert_ingestion_writable()
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "INGESTION_MODE_BLOCKS_WRITES", "message": str(exc)},
        ) from exc
    try:
        enforce_ingestion_write_rate_limit(
            endpoint="/ingest/business-dates", record_count=len(request.business_dates)
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "INGESTION_RATE_LIMIT_EXCEEDED", "message": str(exc)},
        ) from exc
    num_dates = len(request.business_dates)
    job_id = create_ingestion_job_id()
    correlation_id, request_id, trace_id = get_request_lineage()
    job_result = await ingestion_job_service.create_or_get_job(
        job_id=job_id,
        endpoint=str(http_request.url.path),
        entity_type="business_date",
        accepted_count=num_dates,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
        request_id=request_id,
        trace_id=trace_id,
        request_payload=request.model_dump(mode="json"),
    )
    if not job_result.created:
        return build_batch_ack(
            message="Duplicate ingestion request accepted via idempotency replay.",
            entity_type="business_date",
            job_id=job_result.job.job_id,
            accepted_count=job_result.job.accepted_count,
            idempotency_key=idempotency_key,
        )
    logger.info(
        "Received request to ingest business dates.",
        extra={"num_dates": num_dates, "idempotency_key": idempotency_key},
    )

    try:
        await ingestion_service.publish_business_dates(
            request.business_dates, idempotency_key=idempotency_key
        )
        await ingestion_job_service.mark_queued(job_result.job.job_id)
    except IngestionPublishError as exc:
        await ingestion_job_service.mark_failed(
            job_result.job.job_id,
            str(exc),
            failed_record_keys=exc.failed_record_keys,
        )
        raise
    except Exception as exc:
        await ingestion_job_service.mark_failed(job_result.job.job_id, str(exc))
        raise

    logger.info("Business dates successfully queued.", extra={"num_dates": num_dates})
    return build_batch_ack(
        message="Business dates accepted for asynchronous ingestion processing.",
        entity_type="business_date",
        job_id=job_result.job.job_id,
        accepted_count=num_dates,
        idempotency_key=idempotency_key,
    )

