# services/query-service/app/main.py
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from portfolio_common.logging_utils import (
    setup_logging,
    correlation_id_var,
    generate_correlation_id,
)
from portfolio_common.health import create_health_router
from .routers import (
    positions,
    transactions,
    instruments,
    prices,
    fx_rates,
    portfolios,
    performance,
    risk,
    summary,
    review,
    concentration,
    positions_analytics,
    operations,
    integration,
    capabilities,
    lookups,
    simulation,
)

SERVICE_PREFIX = "QRY"
setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages application startup and shutdown events.
    """
    logger.info("Query Service starting up...")
    yield
    logger.info("Query Service shutting down. Waiting for in-flight requests to complete...")
    logger.info("Query Service has shut down gracefully.")


app = FastAPI(
    title="Query Service",
    description="Service for querying portfolio analytics data.",
    version="0.2.0",
    lifespan=lifespan,
)

# --- Prometheus Metrics Instrumentation ---
Instrumentator().instrument(app).expose(app)
logger.info("Prometheus metrics exposed at /metrics")


@app.middleware("http")
async def add_correlation_id_middleware(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-ID")
    if not correlation_id:
        correlation_id = generate_correlation_id(SERVICE_PREFIX)

    token = correlation_id_var.set(correlation_id)
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id
    correlation_id_var.reset(token)
    return response


# Global Exception Handler
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    correlation_id = correlation_id_var.get()
    logger.critical(
        f"Unhandled exception for request {request.method} {request.url}",
        exc_info=exc,
        extra={"correlation_id": correlation_id},
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal Server Error",
            "message": "An unexpected error occurred. Please contact support.",
            "correlation_id": correlation_id,
        },
    )


# Create and include the standardized health router.
# This service depends on the database.
health_router = create_health_router("db")
app.include_router(health_router)

# Register the API routers
app.include_router(portfolios.router)
app.include_router(positions.router)
app.include_router(transactions.router)
app.include_router(instruments.router)
app.include_router(prices.router)
app.include_router(fx_rates.router)
app.include_router(performance.router)
app.include_router(risk.router)
app.include_router(summary.router)
app.include_router(review.router)
app.include_router(concentration.router)
app.include_router(positions_analytics.router)
app.include_router(operations.router)
app.include_router(integration.router)
app.include_router(capabilities.router)
app.include_router(lookups.router)
app.include_router(simulation.router)
