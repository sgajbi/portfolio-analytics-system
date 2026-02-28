# services/ingestion_service/app/routers/business_dates.py
import logging
from typing import Annotated

from app.ack_response import build_batch_ack
from app.DTOs.business_date_dto import BusinessDateIngestionRequest
from app.DTOs.ingestion_ack_dto import BatchIngestionAcceptedResponse
from app.request_metadata import resolve_idempotency_key
from app.services.ingestion_service import IngestionService, get_ingestion_service
from fastapi import APIRouter, Depends, Header, Request, status

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
    idempotency_key_header: Annotated[str | None, Header(alias="X-Idempotency-Key")] = None,
    ingestion_service: IngestionService = Depends(get_ingestion_service),
):
    idempotency_key = idempotency_key_header or resolve_idempotency_key(http_request)
    num_dates = len(request.business_dates)
    logger.info(
        "Received request to ingest business dates.",
        extra={"num_dates": num_dates, "idempotency_key": idempotency_key},
    )

    await ingestion_service.publish_business_dates(
        request.business_dates, idempotency_key=idempotency_key
    )

    logger.info("Business dates successfully queued.", extra={"num_dates": num_dates})
    return build_batch_ack(
        message="Business dates accepted for asynchronous ingestion processing.",
        entity_type="business_date",
        accepted_count=num_dates,
        idempotency_key=idempotency_key,
    )
