# services/ingestion-service/app/routers/transactions.py
import logging
from fastapi import APIRouter, Depends, status
from typing import List

from app.DTOs.transaction_dto import Transaction, TransactionIngestionRequest
from app.services.ingestion_service import IngestionService, get_ingestion_service

logger = logging.getLogger(__name__)
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
        extra={
            "transaction_id": transaction.transaction_id,
            "portfolio_id": transaction.portfolio_id
        }
    )
    
    await ingestion_service.publish_transaction(transaction)

    logger.info("Transaction successfully queued.", extra={"transaction_id": transaction.transaction_id})
    return {
        "message": "Transaction received and queued for processing",
        "transaction_id": transaction.transaction_id
    }

@router.post("/ingest/transactions", status_code=status.HTTP_202_ACCEPTED, tags=["Transactions"])
async def ingest_transactions(
    request: TransactionIngestionRequest,
    ingestion_service: IngestionService = Depends(get_ingestion_service)
):
    """
    Ingests a list of financial transactions and publishes each to a Kafka topic.
    """
    num_transactions = len(request.transactions)
    logger.info("Received request to ingest transactions.", extra={"num_transactions": num_transactions})
    
    await ingestion_service.publish_transactions(request.transactions)
    
    logger.info("Transactions successfully queued.", extra={"num_transactions": num_transactions})
    return {
        "message": f"Successfully queued {num_transactions} transactions for processing."
    }