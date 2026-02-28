# services/ingestion_service/app/routers/instruments.py
import logging

from app.ack_response import build_batch_ack
from app.DTOs.ingestion_ack_dto import BatchIngestionAcceptedResponse
from app.DTOs.instrument_dto import InstrumentIngestionRequest
from app.request_metadata import IdempotencyKeyHeader, resolve_idempotency_key
from app.services.ingestion_service import IngestionService, get_ingestion_service
from fastapi import APIRouter, Depends, Request, status

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/ingest/instruments",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=BatchIngestionAcceptedResponse,
    tags=["Instruments"],
    summary="Ingest instruments",
    description="Accepts canonical instruments and publishes them for asynchronous processing.",
)
async def ingest_instruments(
    request: InstrumentIngestionRequest,
    http_request: Request,
    idempotency_key_header: IdempotencyKeyHeader = None,
    ingestion_service: IngestionService = Depends(get_ingestion_service),
):
    idempotency_key = idempotency_key_header or resolve_idempotency_key(http_request)
    num_instruments = len(request.instruments)
    logger.info(
        "Received request to ingest instruments.",
        extra={"num_instruments": num_instruments, "idempotency_key": idempotency_key},
    )

    await ingestion_service.publish_instruments(
        request.instruments, idempotency_key=idempotency_key
    )

    logger.info("Instruments successfully queued.", extra={"num_instruments": num_instruments})
    return build_batch_ack(
        message="Instruments accepted for asynchronous ingestion processing.",
        entity_type="instrument",
        accepted_count=num_instruments,
        idempotency_key=idempotency_key,
    )
