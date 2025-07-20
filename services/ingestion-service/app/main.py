# services/ingestion-service/app/main.py
from fastapi import FastAPI, HTTPException, Depends, status
from contextlib import asynccontextmanager
import logging

from app.models.transaction import Transaction
from common.config import KAFKA_RAW_TRANSACTIONS_TOPIC
from common.kafka_utils import KafkaProducer, get_kafka_producer

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Define a dictionary to hold application state, including the Kafka producer
# This avoids using global variables and makes state management more explicit.
app_state = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages the application's lifecycle for startup and shutdown events.
    Initializes and closes the Kafka producer.
    """
    logger.info("Ingestion Service starting up...")
    try:
        # Initialize the Kafka producer and store it in the app_state
        app_state["kafka_producer"] = get_kafka_producer()
        logger.info("Kafka producer initialized successfully.")
    except Exception as e:
        logger.critical(f"Failed to initialize Kafka producer on startup: {e}", exc_info=True)
        # Depending on the policy, you might want the app to fail starting up.
        # For now, we log it as critical and let it proceed, but publishing will fail.
        app_state["kafka_producer"] = None

    yield

    # Shutdown event
    logger.info("Ingestion Service shutting down...")
    producer = app_state.get("kafka_producer")
    if producer:
        try:
            remaining = producer.flush(timeout=5)
            if remaining > 0:
                logger.warning(f"Kafka producer flush timed out with {remaining} messages remaining in queue.")
            else:
                logger.info("Kafka producer flushed successfully.")
        except Exception as e:
            logger.error(f"Error flushing Kafka producer during shutdown: {e}", exc_info=True)
    app_state.clear()


app = FastAPI(
    title="Ingestion Service",
    description="Service for ingesting transaction data and publishing it to Kafka.",
    version="0.1.0",
    lifespan=lifespan
)


def get_producer_dependency() -> KafkaProducer:
    """
    FastAPI dependency to get the Kafka producer instance from the app state.
    Raises an exception if the producer is not available, preventing the endpoint
    from attempting to process a request it cannot handle.
    """
    producer = app_state.get("kafka_producer")
    if not producer:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Kafka producer is not available. The service may be starting up or in an error state."
        )
    return producer


@app.get("/health")
async def health_check():
    """Health check endpoint to verify service status."""
    return {"status": "ok", "service": "Ingestion Service"}


@app.post("/ingest/transaction", status_code=status.HTTP_202_ACCEPTED)
async def ingest_transaction(
    transaction: Transaction,
    kafka_producer: KafkaProducer = Depends(get_producer_dependency)
):
    """
    Receives a transaction, validates it, and publishes it to a Kafka topic.
    Returns a 202 Accepted response upon successful queuing.
    """
    logger.info(f"Received transaction: {transaction.transaction_id} for portfolio {transaction.portfolio_id}")

    try:
        # Pydantic model_dump_json serializes the model to a JSON string
        transaction_json_payload = transaction.model_dump_json()

        kafka_producer.publish_message(
            topic=KAFKA_RAW_TRANSACTIONS_TOPIC,
            key=transaction.transaction_id,
            value=transaction_json_payload
        )

        logger.info(f"Transaction {transaction.transaction_id} successfully published to Kafka topic '{KAFKA_RAW_TRANSACTIONS_TOPIC}'.")
        return {
            "message": "Transaction received and queued for processing",
            "transaction_id": transaction.transaction_id
        }

    except Exception as e:
        logger.error(f"Failed to publish transaction {transaction.transaction_id} to Kafka: {e}", exc_info=True)
        # If publishing fails, return a 500 error to the client.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to publish transaction to Kafka: {str(e)}"
        )