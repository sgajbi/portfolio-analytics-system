# services/ingestion_service/app/routers/portfolios.py
import logging
from fastapi import APIRouter, Depends, status

from app.DTOs.portfolio_dto import PortfolioIngestionRequest
from app.services.ingestion_service import IngestionService, get_ingestion_service

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/ingest/portfolios", status_code=status.HTTP_202_ACCEPTED, tags=["Portfolios"])
async def ingest_portfolios(
    request: PortfolioIngestionRequest,
    ingestion_service: IngestionService = Depends(get_ingestion_service)
):
    """
    Ingests a list of portfolios and publishes each to a Kafka topic.
    """
    num_portfolios = len(request.portfolios)
    logger.info("Received request to ingest portfolios.", extra={"num_portfolios": num_portfolios})
    
    await ingestion_service.publish_portfolios(request.portfolios)

    logger.info("Portfolios successfully queued.", extra={"num_portfolios": num_portfolios})
    return {
        "message": f"Successfully queued {num_portfolios} portfolios for processing."
    }