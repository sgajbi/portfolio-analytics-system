# services/ingestion-service/app/routers/market_prices.py
import structlog
from fastapi import APIRouter, Depends, status, HTTPException
from pydantic import ValidationError

from app.DTOs.market_price_dto import MarketPriceIngestionRequest
from app.services.ingestion_service import IngestionService, get_ingestion_service

logger = structlog.get_logger(__name__)
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
    logger.info("Received request to ingest market prices.", num_prices=num_prices)
    try:
        await ingestion_service.publish_market_prices(request.market_prices)
        logger.info("Market prices successfully queued.", num_prices=num_prices)
        return {
            "message": f"Successfully queued {num_prices} market prices for processing."
        }
    except ValidationError as e:
        logger.error("Validation error during market price ingestion.", num_prices=num_prices, error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid market price data: {e.errors()}"
        )
    except Exception as e:
        logger.error("Failed to publish bulk market prices due to an unexpected error.", num_prices=num_prices, error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while processing market prices."
        )