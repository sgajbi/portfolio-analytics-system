import structlog
from fastapi import APIRouter, Depends, status, HTTPException
from pydantic import ValidationError

from app.DTOs.portfolio_dto import PortfolioIngestionRequest
from app.services.ingestion_service import IngestionService, get_ingestion_service

logger = structlog.get_logger(__name__)
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
    logger.info("Received request to ingest portfolios.", num_portfolios=num_portfolios)
    try:
        # This method will be created in the next step
        await ingestion_service.publish_portfolios(request.portfolios)
        logger.info("Portfolios successfully queued.", num_portfolios=num_portfolios)
        return {
            "message": f"Successfully queued {num_portfolios} portfolios for processing."
        }
    except ValidationError as e:
        logger.error("Validation error during portfolio ingestion.", num_portfolios=num_portfolios, error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid portfolio data: {e.errors()}"
        )
    except Exception as e:
        logger.error("Failed to publish bulk portfolios due to an unexpected error.", num_portfolios=num_portfolios, error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while processing portfolios."
        )