# services/ingestion-service/app/routers/transactions.py
import structlog
from fastapi import APIRouter, Depends, status, HTTPException
from typing import List
from pydantic import ValidationError # Import ValidationError

from app.DTOs.transaction_dto import Transaction, TransactionIngestionRequest
from app.services.ingestion_service import IngestionService, get_ingestion_service

logger = structlog.get_logger(__name__)
router = APIRouter()

@router.post("/ingest/transaction", status_code=status.HTTP_202_ACCEPTED, tags=["Transactions"])
async def ingest_transaction(
    transaction: Transaction,
    ingestion_service: IngestionService = Depends(get_ingestion_service)
):
    """
    Ingests a single financial transaction and publishes it to a Kafka topic.
    """
    logger.info(
        "Received single transaction.", 
        transaction_id=transaction.transaction_id, 
        portfolio_id=transaction.portfolio_id
    )
    try:
        await ingestion_service.publish_transaction(transaction)
        logger.info("Transaction successfully queued.", transaction_id=transaction.transaction_id)
        return {
            "message": "Transaction received and queued for processing",
            "transaction_id": transaction.transaction_id
        }
    except ValidationError as e:
        logger.error(
            "Validation error during single transaction ingestion.", 
            transaction_id=transaction.transaction_id, 
            error=str(e), 
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid transaction data: {e.errors()}"
        )
    except Exception as e:
        logger.error(
            "Failed to publish transaction due to an unexpected error.", 
            transaction_id=transaction.transaction_id, 
            error=str(e), 
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while processing the transaction."
        )

# NEW: Add a bulk ingestion endpoint
@router.post("/ingest/transactions", status_code=status.HTTP_202_ACCEPTED, tags=["Transactions"])
async def ingest_transactions(
    request: TransactionIngestionRequest,
    ingestion_service: IngestionService = Depends(get_ingestion_service)
):
    """
    Ingests a list of financial transactions and publishes each to a Kafka topic.
    """
    num_transactions = len(request.transactions)
    logger.info("Received request to ingest transactions.", num_transactions=num_transactions)
    try:
        await ingestion_service.publish_transactions(request.transactions)
        logger.info("Transactions successfully queued.", num_transactions=num_transactions)
        return {
            "message": f"Successfully queued {num_transactions} transactions for processing."
        }
    except ValidationError as e:
        logger.error("Validation error during bulk transactions ingestion.", num_transactions=num_transactions, error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid transactions data: {e.errors()}"
        )
    except Exception as e:
        logger.error("Failed to publish bulk transactions due to an unexpected error.", num_transactions=num_transactions, error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while processing transactions."
        )