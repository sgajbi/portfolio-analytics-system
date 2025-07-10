from fastapi import FastAPI, HTTPException, Depends, status
from contextlib import asynccontextmanager
import logging
from sqlalchemy.orm import Session
from sqlalchemy import text # For testing DB connection

from app.models.transaction import Transaction
from app.database import engine, SessionLocal, Base, get_db # Import Base and get_db
from app import crud # Import crud operations
from common.config import POSTGRES_URL

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
    except Exception as e:
        logger.error(f"Failed to connect to PostgreSQL database: {e}")
        # Depending on criticality, you might want to exit here or implement retry logic

    # No need to call Base.metadata.create_all(bind=engine) here if using Alembic for migrations
    # Base.metadata.create_all(bind=engine) # This line should typically be managed by Alembic

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

@app.post("/ingest/transaction", status_code=status.HTTP_201_CREATED)
async def ingest_transaction(
    transaction: Transaction,
    db: Session = Depends(get_db) # Inject database session
):
    logger.info(f"Received transaction: {transaction.transaction_id} for portfolio {transaction.portfolio_id}")
    try:
        db_transaction = crud.create_transaction(db=db, transaction=transaction)
        logger.info(f"Transaction {db_transaction.transaction_id} saved to DB.")
        return {"message": "Transaction ingested successfully", "transaction_id": db_transaction.transaction_id}
    except Exception as e:
        logger.error(f"Error ingesting transaction {transaction.transaction_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to ingest transaction")