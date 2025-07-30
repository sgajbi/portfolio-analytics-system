# services/ingestion-service/app/routers/fx_rates.py
import structlog
from fastapi import APIRouter, Depends, status, HTTPException
from pydantic import ValidationError # Import ValidationError

from app.DTOs.fx_rate_dto import FxRateIngestionRequest
from app.services.ingestion_service import IngestionService, get_ingestion_service

logger = structlog.get_logger(__name__)
router = APIRouter()

@router.post("/ingest/fx-rates", status_code=status.HTTP_202_ACCEPTED, tags=["FX Rates"])
async def ingest_fx_rates(
    request: FxRateIngestionRequest,
    ingestion_service: IngestionService = Depends(get_ingestion_service)
):
    """
    Ingests a list of FX rates and publishes each to a Kafka topic.
    """
    num_rates = len(request.fx_rates)
    logger.info("Received request to ingest fx rates.", num_rates=num_rates) # [cite: 512]
    try:
        await ingestion_service.publish_fx_rates(request.fx_rates)
        logger.info("FX rates successfully queued.", num_rates=num_rates) # [cite: 512]
        return {
            "message": f"Successfully queued {num_rates} FX rates for processing."
        }
    except ValidationError as e:
        logger.error("Validation error during FX rates ingestion.", num_rates=num_rates, error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid FX rate data: {e.errors()}"
        )
    except Exception as e:
        logger.error("Failed to publish bulk FX rates due to an unexpected error.", num_rates=num_rates, error=str(e), exc_info=True) # [cite: 513]
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while processing FX rates."
        )