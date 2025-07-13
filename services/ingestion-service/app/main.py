from fastapi import FastAPI, HTTPException, Depends, status
from contextlib import asynccontextmanager
import logging
from sqlalchemy.orm import Session
from sqlalchemy import text # For testing DB connection

from app.models.transaction import Transaction
from app.database import engine, SessionLocal, Base, get_db
from app import crud
from common.config import KAFKA_RAW_TRANSACTIONS_TOPIC # <--- New Import
from common.kafka_utils import get_kafka_producer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Application lifecycle events
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup event
    logger.info("Ingestion Service starting up...")
    try:
        # Test database connection on startup
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        logger.info("Successfully connected to PostgreSQL database.")

        # Initialize Kafka Producer
        # Calling this here ensures the producer is ready when the app starts
        # and logs its initialization status.
        producer_instance = get_kafka_producer()
        # No explicit ping for Kafka producer, initialization is usually enough.
        # If Kafka is unavailable, the producer might log connection errors during background operations.

    except Exception as e:
        logger.error(f"Failed critical service startup component (PostgreSQL or Kafka Producer): {e}")
        # Re-raise the exception to prevent the application from starting in a broken state
        raise

    yield
    # Shutdown event
    logger.info("Ingestion Service shutting down...")
    # Flush Kafka producer messages before shutdown
    try:
        producer_instance = get_kafka_producer() # Get the instance to flush
        remaining = producer_instance.flush(timeout=5) # 5-second timeout for flushing
        if remaining > 0:
            logger.warning(f"Kafka producer flush timed out with {remaining} messages remaining in queue.")
        else:
            logger.info("Kafka producer flushed successfully.")
    except Exception as e:
        logger.error(f"Error flushing Kafka producer during shutdown: {e}")
    # Add any other cleanup logic here (e.g., close DB connections, though SQLAlchemy handles pool)

app = FastAPI(
    title="Ingestion Service",
    description="Service for ingesting transaction, instrument, and market data.",
    version="0.1.0",
    lifespan=lifespan
)

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "Ingestion Service"}

@app.post("/ingest/transaction", status_code=status.HTTP_201_CREATED)
async def ingest_transaction(
    transaction: Transaction,
    db: Session = Depends(get_db) # Inject database session
):
    logger.info(f"Received transaction: {transaction.transaction_id} for portfolio {transaction.portfolio_id}")
    try:
        # 1. Save to PostgreSQL
        db_transaction = crud.create_transaction(db=db, transaction=transaction)
        logger.info(f"Transaction {db_transaction.transaction_id} saved to DB.")

        # 2. Publish to Kafka
        kafka_producer = get_kafka_producer()

        # Convert Pydantic model to a JSON string using .model_dump_json()
        # This handles date and datetime serialization to ISO 8601 format.
        transaction_json_string = transaction.model_dump_json()

        # Use transaction_id as key for consistent partitioning
        kafka_producer.publish_message(
            topic=KAFKA_RAW_TRANSACTIONS_TOPIC, # <--- Updated to use config variable
            key=transaction.transaction_id,
            value=transaction_json_string
        )
        logger.info(f"Transaction {transaction.transaction_id} published to Kafka topic '{KAFKA_RAW_TRANSACTIONS_TOPIC}'.")

        return {"message": "Transaction ingested successfully", "transaction_id": db_transaction.transaction_id}
    except Exception as e:
        logger.error(f"Error ingesting or publishing transaction {transaction.transaction_id}: {e}")
        # Raise HTTP 500 if either DB save or Kafka publish fails
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to ingest and publish transaction")