# services/ingestion-service/app/routers/instruments.py
import logging
from fastapi import APIRouter, Depends, status, HTTPException
from pydantic import ValidationError

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
    logger.info("Received request to ingest instruments.", extra={"num_instruments": num_instruments})
    try:
        await ingestion_service.publish_instruments(request.instruments)
        logger.info("Instruments successfully queued.", extra={"num_instruments": num_instruments})
        return {
            "message": f"Successfully queued {num_instruments} instruments for processing."
        }
    except ValidationError as e:
        logger.error("Validation error during instrument ingestion.", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid instrument data: {e.errors()}"
        )
    except Exception as e:
        logger.error("Failed to publish bulk instruments due to an unexpected error.", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while processing instruments."
        )