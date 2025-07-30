# services/ingestion-service/app/routers/fx_rates.py
import structlog
from fastapi import APIRouter, Depends, status, HTTPException

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
    logger.info(f"Received request to ingest fx rates.", num_rates=num_rates)
    try:
        await ingestion_service.publish_fx_rates(request.fx_rates)
        logger.info(f"FX rates successfully queued.", num_rates=num_rates)
        return {
            "message": f"Successfully queued {num_rates} FX rates for processing."
        }
    except Exception as e:
        logger.error("Failed to publish bulk FX rates", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to publish bulk FX rates: {str(e)}"
        )