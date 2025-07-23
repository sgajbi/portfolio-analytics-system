# services/ingestion-service/app/routers/transactions.py
import logging
from fastapi import APIRouter, Depends, status, HTTPException

from app.DTOs.transaction_dto import Transaction
from app.services.ingestion_service import IngestionService, get_ingestion_service

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/ingest/transaction", status_code=status.HTTP_202_ACCEPTED)
async def ingest_transaction(
    transaction: Transaction,
    ingestion_service: IngestionService = Depends(get_ingestion_service)
):
    """
    Ingests a single financial transaction and publishes it to a Kafka topic.
    """
    logger.info(f"Received transaction: {transaction.transaction_id} for portfolio {transaction.portfolio_id}")
    try:
        await ingestion_service.publish_transaction(transaction)
        logger.info(f"Transaction {transaction.transaction_id} successfully queued.")
        return {
            "message": "Transaction received and queued for processing",
            "transaction_id": transaction.transaction_id
        }
    except Exception as e:
        logger.error(f"Failed to publish transaction {transaction.transaction_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to publish transaction: {str(e)}"
        )
        