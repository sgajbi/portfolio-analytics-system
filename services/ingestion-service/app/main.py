# services/ingestion-service/app/main.py
from fastapi import FastAPI, status, HTTPException, Request
from contextlib import asynccontextmanager
import logging

# NEW: Import shared logging utility
from portfolio_common.logging_utils import setup_logging, correlation_id_var, generate_correlation_id
from portfolio_common.kafka_utils import get_kafka_producer, KafkaProducer
from app.routers import transactions, instruments, market_prices, fx_rates, portfolios

SERVICE_PREFIX = "ING"
setup_logging()
logger = logging.getLogger(__name__)

# Application state
app_state = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Ingestion Service starting up...")
    try:
        app_state["kafka_producer"] = get_kafka_producer()
        logger.info("Kafka producer initialized successfully.")
    except Exception as e:
        logger.critical("Failed to initialize Kafka producer on startup", exc_info=True)
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
    version="0.5.0",
    lifespan=lifespan
)

# Correlation ID Middleware
@app.middleware("http")
async def add_correlation_id_middleware(request: Request, call_next):
    correlation_id = request.headers.get('X-Correlation-ID')
    if not correlation_id:
        correlation_id = generate_correlation_id(SERVICE_PREFIX)
    
    token = correlation_id_var.set(correlation_id)
    
    response = await call_next(request)
    response.headers['X-Correlation-ID'] = correlation_id
    
    correlation_id_var.reset(token)
    
    return response

# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "Ingestion Service"}

# Include the API routers
app.include_router(portfolios.router)
app.include_router(transactions.router)
app.include_router(instruments.router)
app.include_router(market_prices.router)
app.include_router(fx_rates.router)

# Custom dependency
def get_producer_dependency() -> KafkaProducer:
    producer = app_state.get("kafka_producer")
    if not producer:
        logger.error("Kafka producer is not available")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Kafka producer is not available. The service may be starting up or in a failed state."
        )
    return producer

app.dependency_overrides[get_kafka_producer] = get_producer_dependency