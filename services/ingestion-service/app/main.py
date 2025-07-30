# services/ingestion-service/app/main.py
from fastapi import FastAPI, status, HTTPException, Request
from contextlib import asynccontextmanager
import logging
import uuid
import sys

import structlog
from pythonjsonlogger import jsonlogger

# --- Updated: Import from the new context file ---
from .context import correlation_id_cv
from portfolio_common.kafka_utils import get_kafka_producer, KafkaProducer
from app.routers import transactions, instruments, market_prices, fx_rates, portfolios

# --- New: Structured Logging Configuration ---
def configure_logging():
    """
    Configures structured logging using structlog.
    Logs will be in JSON format and will automatically include the correlation ID.
    """
    # Define a processor to add the correlation ID from our context variable
    def add_correlation_id(logger, method_name, event_dict):
        correlation_id = correlation_id_cv.get()
        if correlation_id:
            event_dict['correlation_id'] = correlation_id
        return event_dict

    # Configure standard logging to be handled by structlog
    logging.basicConfig(handlers=[logging.StreamHandler(sys.stdout)], level=logging.INFO, format="%(message)s")

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            add_correlation_id, # Add our custom processor
            structlog.stdlib.render_to_log_kwargs,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # Use a JSON formatter for the root logger
    handler = logging.StreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter()
    handler.setFormatter(formatter)
    
    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(logging.INFO)

    logger = structlog.get_logger("ingestion-service")
    logger.info("Structured logging configured.")

# Use the new logger
logger = structlog.get_logger(__name__)

# Application state
app_state = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Configure logging on startup
    configure_logging()
    logger.info("Ingestion Service starting up...")
    try:
        app_state["kafka_producer"] = get_kafka_producer()
        logger.info("Kafka producer initialized successfully.")
    except Exception as e:
        logger.critical("Failed to initialize Kafka producer on startup", error=str(e), exc_info=True)
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
        correlation_id = str(uuid.uuid4())
    
    token = correlation_id_cv.set(correlation_id)
    
    response = await call_next(request)
    response.headers['X-Correlation-ID'] = correlation_id
    
    correlation_id_cv.reset(token)
    
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