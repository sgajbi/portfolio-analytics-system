# services/ingestion-service/app/main.py
from fastapi import FastAPI, status, HTTPException, Request
from contextlib import asynccontextmanager
import logging
import uuid
import contextvars

from portfolio_common.kafka_utils import get_kafka_producer, KafkaProducer
from app.routers import transactions, instruments, market_prices, fx_rates, portfolios

# --- New: ContextVar for Correlation ID ---
correlation_id_cv = contextvars.ContextVar('correlation_id', default=None)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Application state to hold the Kafka producer
app_state = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handles startup and shutdown events.
    Initializes the Kafka producer on startup and flushes it on shutdown.
    """
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

# Main FastAPI app instance
app = FastAPI(
    title="Ingestion Service",
    description="Service for ingesting financial data and publishing it to Kafka.",
    version="0.5.0", # Version bump for new feature
    lifespan=lifespan
)

# --- New: Correlation ID Middleware ---
@app.middleware("http")
async def add_correlation_id_middleware(request: Request, call_next):
    """
    Checks for a correlation ID header or generates a new one.
    Stores it in a context variable for use throughout the request lifecycle.
    """
    correlation_id = request.headers.get('X-Correlation-ID')
    if not correlation_id:
        correlation_id = str(uuid.uuid4())
    
    # Store the ID in the context variable
    token = correlation_id_cv.set(correlation_id)
    
    response = await call_next(request)
    response.headers['X-Correlation-ID'] = correlation_id
    
    # Reset the context variable after the request is done
    correlation_id_cv.reset(token)
    
    return response

# Health check endpoint
@app.get("/health")
async def health_check():
    """Returns the operational status of the service."""
    return {"status": "ok", "service": "Ingestion Service"}

# Include the API routers
app.include_router(portfolios.router)
app.include_router(transactions.router)
app.include_router(instruments.router)
app.include_router(market_prices.router)
app.include_router(fx_rates.router)

# Custom dependency to provide the Kafka producer and handle unavailability
def get_producer_dependency() -> KafkaProducer:
    producer = app_state.get("kafka_producer")
    if not producer:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Kafka producer is not available. The service may be starting up or in a failed state."
        )
    return producer

# Update the dependency overrides for the entire app
# This ensures that get_kafka_producer from portfolio-common is correctly managed.
app.dependency_overrides[get_kafka_producer] = get_producer_dependency