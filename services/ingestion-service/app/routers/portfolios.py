import logging
from fastapi import APIRouter, Depends, status, HTTPException

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
    logger.info(f"Received request to ingest {num_portfolios} portfolios.")
    try:
        # This method will be created in the next step
        await ingestion_service.publish_portfolios(request.portfolios)
        logger.info(f"{num_portfolios} portfolios successfully queued.")
        return {
            "message": f"Successfully queued {num_portfolios} portfolios for processing."
        }
    except Exception as e:
        logger.error(f"Failed to publish bulk portfolios: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to publish bulk portfolios: {str(e)}"
        )