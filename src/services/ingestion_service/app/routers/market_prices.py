# services/ingestion_service/app/routers/market_prices.py
import logging
from fastapi import APIRouter, Depends, status

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
    logger.info("Received request to ingest market prices.", extra={"num_prices": num_prices})
    
    await ingestion_service.publish_market_prices(request.market_prices)

    logger.info("Market prices successfully queued.", extra={"num_prices": num_prices})
    return {
        "message": f"Successfully queued {num_prices} market prices for processing."
    }