import logging

from app.ack_response import build_batch_ack
from app.DTOs.ingestion_ack_dto import BatchIngestionAcceptedResponse
from app.DTOs.portfolio_dto import PortfolioIngestionRequest
from app.request_metadata import IdempotencyKeyHeader, resolve_idempotency_key
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
):
    idempotency_key = idempotency_key_header or resolve_idempotency_key(http_request)
    num_portfolios = len(request.portfolios)
    logger.info(
        "Received request to ingest portfolios.",
        extra={"num_portfolios": num_portfolios, "idempotency_key": idempotency_key},
    )

    await ingestion_service.publish_portfolios(request.portfolios, idempotency_key=idempotency_key)

    logger.info("Portfolios successfully queued.", extra={"num_portfolios": num_portfolios})
    return build_batch_ack(
        message="Portfolios accepted for asynchronous ingestion processing.",
        entity_type="portfolio",
        accepted_count=num_portfolios,
        idempotency_key=idempotency_key,
    )
