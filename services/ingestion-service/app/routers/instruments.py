# services/ingestion-service/app/routers/instruments.py
import logging
from fastapi import APIRouter, Depends, status, HTTPException

from app.DTOs.instrument_dto import InstrumentIngestionRequest
from app.services.ingestion_service import IngestionService, get_ingestion_service

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/ingest/instruments", status_code=status.HTTP_202_ACCEPTED, tags=["Instruments"])
async def ingest_instruments(
    request: InstrumentIngestionRequest,
    ingestion_service: IngestionService = Depends(get_ingestion_service)
):
    """
    Ingests a list of financial instruments and publishes each to a Kafka topic.
    """
    num_instruments = len(request.instruments)
    logger.info(f"Received request to ingest {num_instruments} instruments.")
    try:
        await ingestion_service.publish_instruments(request.instruments)
        logger.info(f"{num_instruments} instruments successfully queued.")
        return {
            "message": f"Successfully queued {num_instruments} instruments for processing."
        }
    except Exception as e:
        logger.error(f"Failed to publish bulk instruments: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to publish bulk instruments: {str(e)}"
        )