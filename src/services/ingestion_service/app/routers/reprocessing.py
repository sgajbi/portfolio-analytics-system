# src/services/ingestion_service/app/routers/reprocessing.py
import logging
from fastapi import APIRouter, Depends, status
from portfolio_common.kafka_utils import KafkaProducer, get_kafka_producer
from portfolio_common.logging_utils import correlation_id_var
from ..DTOs.reprocessing_dto import ReprocessingRequest

logger = logging.getLogger(__name__)
router = APIRouter()

# Define the new topic name
REPROCESSING_REQUESTED_TOPIC = "transactions_reprocessing_requested"

@router.post("/reprocess/transactions", status_code=status.HTTP_202_ACCEPTED, tags=["Reprocessing"])
async def reprocess_transactions(
    request: ReprocessingRequest,
    kafka_producer: KafkaProducer = Depends(get_kafka_producer)
):
    """
    Accepts a list of transaction IDs and publishes a reprocessing request
    event for each to a Kafka topic.
    """
    num_to_reprocess = len(request.transaction_ids)
    correlation_id = correlation_id_var.get()
    headers = [('correlation_id', (correlation_id or "").encode('utf-8'))] if correlation_id else []
    
    logger.info(f"Received request to reprocess {num_to_reprocess} transaction(s).")
    
    for txn_id in request.transaction_ids:
        event_payload = {"transaction_id": txn_id}
        kafka_producer.publish_message(
            topic=REPROCESSING_REQUESTED_TOPIC,
            key=txn_id, # Key by transaction_id for partitioning
            value=event_payload,
            headers=headers
        )
    
    kafka_producer.flush(timeout=5)
    
    logger.info(f"Successfully queued {num_to_reprocess} reprocessing requests.")
    return {
        "message": f"Successfully queued {num_to_reprocess} transactions for reprocessing."
    }