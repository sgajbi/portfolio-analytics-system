from fastapi import FastAPI, HTTPException, Depends, status
from contextlib import asynccontextmanager
import logging
from sqlalchemy.orm import Session
from sqlalchemy import text # For testing DB connection

from app.models.transaction import Transaction
# from app.database import engine, SessionLocal, Base, get_db # <--- Remove or comment out DB imports
from common.config import KAFKA_RAW_TRANSACTIONS_TOPIC
from common.kafka_utils import get_kafka_producer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Application lifecycle events
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup event
    logger.info("Ingestion Service starting up...")
    try:
        # Test database connection on startup (this service still needs to know if DB is up for Alembic, but not for direct writes)
        # However, for pure ingestion, this check can be removed if the service doesn't directly interact with DB.
        # For now, keeping it as Alembic migration still runs from this service on startup
        # To avoid dependency issues: The ingestion service itself does not need the DB connection,
        # but its Docker entrypoint runs Alembic, which needs it. So, keep the check here.
        # Ensure common.db_utils is imported if needed for this check, but for now, it's simpler
        # if the service itself doesn't need get_db or direct engine access in its FastAPI routes.

        # For the purpose of this refactor, let's remove the direct DB connection check in lifespan
        # as the ingestion service will no longer directly interact with it.
        # Alembic will still run from the docker-compose command, so it needs access,
        # but the FastAPI app itself doesn't.

        # Initialize Kafka Producer
        producer_instance = get_kafka_producer()

    except Exception as e:
        logger.error(f"Failed critical service startup component (Kafka Producer): {e}")
        raise

    yield
    # Shutdown event
    logger.info("Ingestion Service shutting down...")
    try:
        producer_instance = get_kafka_producer()
        remaining = producer_instance.flush(timeout=5)
        if remaining > 0:
            logger.warning(f"Kafka producer flush timed out with {remaining} messages remaining in queue.")
        else:
            logger.info("Kafka producer flushed successfully.")
    except Exception as e:
        logger.error(f"Error flushing Kafka producer during shutdown: {e}")

app = FastAPI(
    title="Ingestion Service",
    description="Service for ingesting transaction, instrument, and market data.",
    version="0.1.0",
    lifespan=lifespan
)

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "Ingestion Service"}

@app.post("/ingest/transaction", status_code=status.HTTP_202_ACCEPTED) # Changed to 202 Accepted
async def ingest_transaction(
    transaction: Transaction,
    # db: Session = Depends(get_db) # <--- Remove DB dependency
):
    logger.info(f"Received transaction: {transaction.transaction_id} for portfolio {transaction.portfolio_id}")
    try:
        # 1. Removed: Save to PostgreSQL - This is now handled by Transaction Persistence Service
        # db_transaction = crud.create_transaction(db=db, transaction=transaction)
        # logger.info(f"Transaction {db_transaction.transaction_id} saved to DB.")

        # 2. Publish to Kafka
        kafka_producer = get_kafka_producer()
        transaction_json_string = transaction.model_dump_json()

        kafka_producer.publish_message(
            topic=KAFKA_RAW_TRANSACTIONS_TOPIC,
            key=transaction.transaction_id,
            value=transaction_json_string
        )
        logger.info(f"Transaction {transaction.transaction_id} published to Kafka topic '{KAFKA_RAW_TRANSACTIONS_TOPIC}'.")

        # Changed response message
        return {"message": "Transaction received and queued for persistence", "transaction_id": transaction.transaction_id}
    except Exception as e:
        logger.error(f"Error ingesting or publishing transaction {transaction.transaction_id}: {e}")
        # Only raise HTTP 500 if Kafka publish fails
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to ingest and publish transaction to Kafka")