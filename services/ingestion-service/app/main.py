# services/ingestion-service/app/main.py
import logging
from contextlib import asynccontextmanager
import asyncio

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator # <-- NEW IMPORT
from portfolio_common.kafka_utils import get_kafka_producer, KafkaProducer
from portfolio_common.logging_utils import setup_logging, correlation_id_var, generate_correlation_id
from portfolio_common.config import KAFKA_BOOTSTRAP_SERVERS
from app.routers import transactions, instruments, market_prices, fx_rates, portfolios
from confluent_kafka.admin import AdminClient

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

# --- NEW: Add Prometheus Metrics ---
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

async def check_kafka_health():
    """Checks if a connection can be established with Kafka."""
    try:
        conf = {'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS}
        admin_client = AdminClient(conf)
        await asyncio.to_thread(admin_client.list_topics, timeout=5)
        return True
    except Exception as e:
        logger.error(f"Health Check: Kafka connection failed: {e}", exc_info=False)
        return False

# Enhanced health check endpoint (now a readiness probe)
@app.get("/health", tags=["Health"])
async def health_check():
    """
    Checks the health and readiness of the service.
    Returns OK if the service is running and can connect to Kafka.
    """
    kafka_ok = await check_kafka_health()
    if kafka_ok:
        return {"status": "ok", "dependencies": {"kafka": "ok"}}
    return JSONResponse(
        status_code=503,
        content={"status": "unavailable", "dependencies": {"kafka": "unavailable"}}
    )


# Include the API routers
app.include_router(portfolios.router)
app.include_router(transactions.router)
app.include_router(instruments.router)
app.include_router(market_prices.router)
app.include_router(fx_rates.router)