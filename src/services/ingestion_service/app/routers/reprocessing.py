# src/services/ingestion_service/app/routers/reprocessing.py
import logging

from app.ack_response import build_batch_ack
from app.DTOs.ingestion_ack_dto import BatchIngestionAcceptedResponse
from app.request_metadata import (
    IdempotencyKeyHeader,
    create_ingestion_job_id,
    get_request_lineage,
    resolve_idempotency_key,
)
from app.services.ingestion_job_service import IngestionJobService, get_ingestion_job_service
from fastapi import APIRouter, Depends, Request, status
from portfolio_common.kafka_utils import KafkaProducer, get_kafka_producer

from ..DTOs.reprocessing_dto import ReprocessingRequest

logger = logging.getLogger(__name__)
router = APIRouter()

# Define the new topic name
REPROCESSING_REQUESTED_TOPIC = "transactions_reprocessing_requested"


@router.post(
    "/reprocess/transactions",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=BatchIngestionAcceptedResponse,
    tags=["Reprocessing"],
    summary="Request transaction reprocessing",
    description=(
        "Accepts transaction identifiers and publishes reprocessing requests "
        "for asynchronous handling."
    ),
)
async def reprocess_transactions(
    request: ReprocessingRequest,
    http_request: Request,
    idempotency_key_header: IdempotencyKeyHeader = None,
    kafka_producer: KafkaProducer = Depends(get_kafka_producer),
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
):
    """
    Accepts a list of transaction IDs and publishes a reprocessing request
    event for each to a Kafka topic.
    """
    num_to_reprocess = len(request.transaction_ids)
    idempotency_key = idempotency_key_header or resolve_idempotency_key(http_request)
    correlation_id, request_id, trace_id = get_request_lineage()
    job_id = create_ingestion_job_id()
    await ingestion_job_service.create_job(
        job_id=job_id,
        endpoint=str(http_request.url.path),
        entity_type="reprocessing_request",
        accepted_count=num_to_reprocess,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
        request_id=request_id,
        trace_id=trace_id,
    )
    headers: list[tuple[str, bytes]] = []
    if correlation_id:
        headers.append(("correlation_id", correlation_id.encode("utf-8")))
    if idempotency_key:
        headers.append(("idempotency_key", idempotency_key.encode("utf-8")))

    logger.info(f"Received request to reprocess {num_to_reprocess} transaction(s).")

    try:
        for txn_id in request.transaction_ids:
            event_payload = {"transaction_id": txn_id}
            kafka_producer.publish_message(
                topic=REPROCESSING_REQUESTED_TOPIC,
                key=txn_id,  # Key by transaction_id for partitioning
                value=event_payload,
                headers=headers or None,
            )

        kafka_producer.flush(timeout=5)
        await ingestion_job_service.mark_queued(job_id)
    except Exception as exc:
        await ingestion_job_service.mark_failed(job_id, str(exc))
        raise

    logger.info(f"Successfully queued {num_to_reprocess} reprocessing requests.")
    return build_batch_ack(
        message=f"Successfully queued {num_to_reprocess} transactions for reprocessing.",
        entity_type="reprocessing_request",
        job_id=job_id,
        accepted_count=num_to_reprocess,
        idempotency_key=idempotency_key,
    )

