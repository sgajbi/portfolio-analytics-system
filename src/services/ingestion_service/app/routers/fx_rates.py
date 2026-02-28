# services/ingestion_service/app/routers/fx_rates.py
import logging
from typing import Annotated

from app.ack_response import build_batch_ack
from app.DTOs.fx_rate_dto import FxRateIngestionRequest
from app.DTOs.ingestion_ack_dto import BatchIngestionAcceptedResponse
from app.request_metadata import resolve_idempotency_key
from app.services.ingestion_service import IngestionService, get_ingestion_service
from fastapi import APIRouter, Depends, Header, Request, status

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
    idempotency_key_header: Annotated[str | None, Header(alias="X-Idempotency-Key")] = None,
    ingestion_service: IngestionService = Depends(get_ingestion_service),
):
    idempotency_key = idempotency_key_header or resolve_idempotency_key(http_request)
    num_rates = len(request.fx_rates)
    logger.info(
        "Received request to ingest fx rates.",
        extra={"num_rates": num_rates, "idempotency_key": idempotency_key},
    )

    await ingestion_service.publish_fx_rates(request.fx_rates, idempotency_key=idempotency_key)

    logger.info("FX rates successfully queued.", extra={"num_rates": num_rates})
    return build_batch_ack(
        message="FX rates accepted for asynchronous ingestion processing.",
        entity_type="fx_rate",
        accepted_count=num_rates,
        idempotency_key=idempotency_key,
    )
