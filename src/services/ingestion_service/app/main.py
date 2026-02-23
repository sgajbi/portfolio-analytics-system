# services/ingestion_service/app/main.py
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from portfolio_common.kafka_utils import get_kafka_producer
from portfolio_common.logging_utils import setup_logging, correlation_id_var, generate_correlation_id
from portfolio_common.health import create_health_router
from app.routers import (
    transactions,
    instruments,
    market_prices,
    fx_rates,
    portfolios,
    business_dates,
    reprocessing,
    portfolio_bundle,
)

SERVICE_PREFIX = "ING"
setup_logging()
logger = logging.getLogger(__name__)

# Application state to hold shared resources like the producer
app_state = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages application startup and shutdown events for graceful operation.
    """
    logger.info("Ingestion Service starting up...")
    try:
        app_state["kafka_producer"] = get_kafka_producer()
        logger.info("Kafka producer initialized successfully.")
    except Exception:
        logger.critical("FATAL: Could not initialize Kafka producer on startup.", exc_info=True)
        app_state["kafka_producer"] = None
    
    yield
    
    logger.info("Ingestion Service shutting down...")
    producer = app_state.get("kafka_producer")
    if producer:
        logger.info("Flushing Kafka producer to send all buffered messages...")
        producer.flush(timeout=5)
    logger.info("Kafka producer flushed successfully.")
    logger.info("Ingestion Service has shut down gracefully.")

# Main FastAPI app instance
app = FastAPI(
    title="Ingestion Service",
    description="Service for ingesting financial data and publishing it to Kafka.",
    version="0.5.0",
    lifespan=lifespan
)

# --- Prometheus Metrics ---
Instrumentator().instrument(app).expose(app)
logger.info("Prometheus metrics exposed at /metrics")

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

# Global Exception Handler
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """
    Catches any unhandled exceptions and returns a standardized 500 error response.
    """
    correlation_id = correlation_id_var.get()
    logger.critical(
        f"Unhandled exception for request {request.method} {request.url}",
        exc_info=exc,
        extra={"correlation_id": correlation_id}
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal Server Error",
            "message": "An unexpected error occurred. Please contact support.",
            "correlation_id": correlation_id
        },
    )

# Create and include the standardized health router.
# This service depends on Kafka.
health_router = create_health_router('kafka')
app.include_router(health_router)

# Include the API routers
app.include_router(portfolios.router)
app.include_router(transactions.router)
app.include_router(instruments.router)
app.include_router(market_prices.router)
app.include_router(fx_rates.router)
app.include_router(business_dates.router)
app.include_router(reprocessing.router) 
app.include_router(portfolio_bundle.router)
