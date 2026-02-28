# services/ingestion_service/app/routers/fx_rates.py
import logging

from app.ack_response import build_batch_ack
from app.DTOs.fx_rate_dto import FxRateIngestionRequest
from app.DTOs.ingestion_ack_dto import BatchIngestionAcceptedResponse
from app.request_metadata import (
    IdempotencyKeyHeader,
    create_ingestion_job_id,
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
    "/ingest/fx-rates",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=BatchIngestionAcceptedResponse,
    tags=["FX Rates"],
    summary="Ingest FX rates",
    description="Accepts canonical FX rates and publishes them for asynchronous processing.",
)
async def ingest_fx_rates(
    request: FxRateIngestionRequest,
    http_request: Request,
    idempotency_key_header: IdempotencyKeyHeader = None,
    ingestion_service: IngestionService = Depends(get_ingestion_service),
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
):
    idempotency_key = idempotency_key_header or resolve_idempotency_key(http_request)
    try:
        await ingestion_job_service.assert_ingestion_writable()
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "INGESTION_MODE_BLOCKS_WRITES", "message": str(exc)},
        ) from exc
    num_rates = len(request.fx_rates)
    job_id = create_ingestion_job_id()
    correlation_id, request_id, trace_id = get_request_lineage()
    job_result = await ingestion_job_service.create_or_get_job(
        job_id=job_id,
        endpoint=str(http_request.url.path),
        entity_type="fx_rate",
        accepted_count=num_rates,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
        request_id=request_id,
        trace_id=trace_id,
        request_payload=request.model_dump(mode="json"),
    )
    if not job_result.created:
        return build_batch_ack(
            message="Duplicate ingestion request accepted via idempotency replay.",
            entity_type="fx_rate",
            job_id=job_result.job.job_id,
            accepted_count=job_result.job.accepted_count,
            idempotency_key=idempotency_key,
        )
    logger.info(
        "Received request to ingest fx rates.",
        extra={"num_rates": num_rates, "idempotency_key": idempotency_key},
    )

    try:
        await ingestion_service.publish_fx_rates(request.fx_rates, idempotency_key=idempotency_key)
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

    logger.info("FX rates successfully queued.", extra={"num_rates": num_rates})
    return build_batch_ack(
        message="FX rates accepted for asynchronous ingestion processing.",
        entity_type="fx_rate",
        job_id=job_result.job.job_id,
        accepted_count=num_rates,
        idempotency_key=idempotency_key,
    )

