# services/ingestion_service/app/routers/business_dates.py
import logging
from fastapi import APIRouter, Depends, status

from app.DTOs.business_date_dto import BusinessDateIngestionRequest
from app.services.ingestion_service import IngestionService, get_ingestion_service

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/ingest/business-dates", status_code=status.HTTP_202_ACCEPTED, tags=["Business Dates"])
async def ingest_business_dates(
    request: BusinessDateIngestionRequest,
    ingestion_service: IngestionService = Depends(get_ingestion_service)
):
    """
    Ingests a list of business dates and publishes each to a Kafka topic.
    """
    num_dates = len(request.business_dates)
    logger.info("Received request to ingest business dates.", extra={"num_dates": num_dates})
    
    await ingestion_service.publish_business_dates(request.business_dates)
    
    logger.info("Business dates successfully queued.", extra={"num_dates": num_dates})
    return {
        "message": f"Successfully queued {num_dates} business dates for processing."
    }