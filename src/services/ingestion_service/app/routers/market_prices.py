# services/ingestion_service/app/routers/market_prices.py
import logging

from app.ack_response import build_batch_ack
from app.DTOs.ingestion_ack_dto import BatchIngestionAcceptedResponse
from app.DTOs.market_price_dto import MarketPriceIngestionRequest
from app.request_metadata import IdempotencyKeyHeader, resolve_idempotency_key
from app.services.ingestion_service import IngestionService, get_ingestion_service
from fastapi import APIRouter, Depends, Request, status

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/ingest/market-prices",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=BatchIngestionAcceptedResponse,
    tags=["Market Prices"],
    summary="Ingest market prices",
    description="Accepts canonical market prices and publishes them for asynchronous processing.",
)
async def ingest_market_prices(
    request: MarketPriceIngestionRequest,
    http_request: Request,
    idempotency_key_header: IdempotencyKeyHeader = None,
    ingestion_service: IngestionService = Depends(get_ingestion_service),
):
    idempotency_key = idempotency_key_header or resolve_idempotency_key(http_request)
    num_prices = len(request.market_prices)
    logger.info(
        "Received request to ingest market prices.",
        extra={"num_prices": num_prices, "idempotency_key": idempotency_key},
    )

    await ingestion_service.publish_market_prices(
        request.market_prices, idempotency_key=idempotency_key
    )

    logger.info("Market prices successfully queued.", extra={"num_prices": num_prices})
    return build_batch_ack(
        message="Market prices accepted for asynchronous ingestion processing.",
        entity_type="market_price",
        accepted_count=num_prices,
        idempotency_key=idempotency_key,
    )
