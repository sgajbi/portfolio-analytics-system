from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager
import logging

from app.models.transaction import Transaction
from common.config import POSTGRES_URL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Application lifecycle events
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup event
    logger.info("Ingestion Service starting up...")
    # Add any startup logic here (e.g., DB connections, Kafka consumer setup)
    logger.info(f"Using Postgres URL: {POSTGRES_URL}") # Just for demonstration
    yield
    # Shutdown event
    logger.info("Ingestion Service shutting down...")
    # Add any cleanup logic here (e.g., close DB connections)

app = FastAPI(
    title="Ingestion Service",
    description="Service for ingesting transaction, instrument, and market data.",
    version="0.1.0",
    lifespan=lifespan
)

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "Ingestion Service"}

@app.post("/ingest/transaction")
async def ingest_transaction(transaction: Transaction):
    logger.info(f"Received transaction: {transaction.transaction_id} for portfolio {transaction.portfolio_id}")
    # In future steps, this is where we'd add logic to:
    # 1. Validate data further
    # 2. Store in database
    # 3. Publish event to Kafka
    return {"message": "Transaction received (not yet processed)", "transaction_id": transaction.transaction_id}