# services/ingestion-service/app/routers/market_prices.py
import logging
from fastapi import APIRouter, Depends, status, HTTPException

from app.DTOs.market_price_dto import MarketPriceIngestionRequest
from app.services.ingestion_service import IngestionService, get_ingestion_service

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/ingest/market-prices", status_code=status.HTTP_202_ACCEPTED, tags=["Market Prices"])
async def ingest_market_prices(
    request: MarketPriceIngestionRequest,
    ingestion_service: IngestionService = Depends(get_ingestion_service)
):
    """
    Ingests a list of market prices and publishes each to a Kafka topic.
    """
    num_prices = len(request.market_prices)
    logger.info(f"Received request to ingest {num_prices} market prices.")
    try:
        await ingestion_service.publish_market_prices(request.market_prices)
        logger.info(f"{num_prices} market prices successfully queued.")
        return {
            "message": f"Successfully queued {num_prices} market prices for processing."
        }
    except Exception as e:
        logger.error(f"Failed to publish bulk market prices: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to publish bulk market prices: {str(e)}"
        )