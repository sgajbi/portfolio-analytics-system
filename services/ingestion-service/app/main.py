# services/ingestion-service/app/main.py
from fastapi import FastAPI, HTTPException, Depends, status
from contextlib import asynccontextmanager
import logging

from app.models.transaction import Transaction
from common.config import KAFKA_RAW_TRANSACTIONS_TOPIC
from common.kafka_utils import KafkaProducer, get_kafka_producer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app_state = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Ingestion Service starting up...")
    try:
        app_state["kafka_producer"] = get_kafka_producer()
        logger.info("Kafka producer initialized successfully.")
    except Exception as e:
        logger.critical(f"Failed to initialize Kafka producer on startup: {e}", exc_info=True)
        app_state["kafka_producer"] = None
    yield
    logger.info("Ingestion Service shutting down...")
    producer = app_state.get("kafka_producer")
    if producer:
        producer.flush(timeout=5)
        logger.info("Kafka producer flushed.")

app = FastAPI(
    title="Ingestion Service",
    description="Service for ingesting transaction data and publishing it to Kafka.",
    version="0.1.0",
    lifespan=lifespan
)

def get_producer_dependency() -> KafkaProducer:
    producer = app_state.get("kafka_producer")
    if not producer:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Kafka producer is not available.")
    return producer

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "Ingestion Service"}

@app.post("/ingest/transaction", status_code=status.HTTP_202_ACCEPTED)
async def ingest_transaction(
    transaction: Transaction,
    kafka_producer: KafkaProducer = Depends(get_producer_dependency)
):
    logger.info(f"Received transaction: {transaction.transaction_id} for portfolio {transaction.portfolio_id}")
    try:
        # --- THIS IS THE FIX ---
        # Use model_dump() to get a dictionary, not model_dump_json()
        transaction_payload = transaction.model_dump()

        kafka_producer.publish_message(
            topic=KAFKA_RAW_TRANSACTIONS_TOPIC,
            key=transaction.transaction_id,
            value=transaction_payload  # Pass the dictionary
        )
        logger.info(f"Transaction {transaction.transaction_id} successfully published to Kafka topic '{KAFKA_RAW_TRANSACTIONS_TOPIC}'.")
        return {
            "message": "Transaction received and queued for processing",
            "transaction_id": transaction.transaction_id
        }
    except Exception as e:
        logger.error(f"Failed to publish transaction {transaction.transaction_id} to Kafka: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to publish transaction to Kafka: {str(e)}")