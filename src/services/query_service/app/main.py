# services/query-service/app/main.py
import logging
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request, status
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from portfolio_common.health import create_health_router
from portfolio_common.logging_utils import (
    correlation_id_var,
    generate_correlation_id,
    request_id_var,
    setup_logging,
    trace_id_var,
)
from portfolio_common.monitoring import HTTP_REQUEST_LATENCY_SECONDS, HTTP_REQUESTS_TOTAL
from prometheus_fastapi_instrumentator import Instrumentator

from .enterprise_readiness import (
    build_enterprise_audit_middleware,
    validate_enterprise_runtime_config,
)
from .routers import (
    capabilities,
    concentration,
    fx_rates,
    instruments,
    integration,
    lookups,
    operations,
    performance,
    portfolios,
    positions,
    positions_analytics,
    prices,
    review,
    risk,
    simulation,
    summary,
    transactions,
)

SERVICE_PREFIX = "QRY"
SERVICE_NAME = "query_service"
setup_logging()
logger = logging.getLogger(__name__)
validate_enterprise_runtime_config()


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
app.middleware("http")(build_enterprise_audit_middleware())

# --- Prometheus Metrics Instrumentation ---
Instrumentator().instrument(app).expose(app)
logger.info("Prometheus metrics exposed at /metrics")


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    metrics_response = (
        schema.get("paths", {}).get("/metrics", {}).get("get", {}).get("responses", {}).get("200")
    )
    if isinstance(metrics_response, dict):
        metrics_response["content"] = {"text/plain": {"schema": {"type": "string"}}}
    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = custom_openapi


@app.middleware("http")
async def add_correlation_id_middleware(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-Id") or request.headers.get(
        "X-Correlation-ID"
    )
    if not correlation_id:
        correlation_id = generate_correlation_id(SERVICE_PREFIX)
    request_id = request.headers.get("X-Request-Id") or generate_correlation_id("REQ")
    trace_id = request.headers.get("X-Trace-Id") or uuid4().hex

    correlation_token = correlation_id_var.set(correlation_id)
    request_token = request_id_var.set(request_id)
    trace_token = trace_id_var.set(trace_id)
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id
    response.headers["X-Correlation-Id"] = correlation_id
    response.headers["X-Request-Id"] = request_id
    response.headers["X-Trace-Id"] = trace_id
    response.headers["traceparent"] = f"00-{trace_id}-0000000000000001-01"
    correlation_id_var.reset(correlation_token)
    request_id_var.reset(request_token)
    trace_id_var.reset(trace_token)
    return response


@app.middleware("http")
async def emit_http_observability(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - start

    labels = {
        "service": SERVICE_NAME,
        "method": request.method,
        "path": request.url.path,
    }
    HTTP_REQUEST_LATENCY_SECONDS.labels(**labels).observe(elapsed)
    HTTP_REQUESTS_TOTAL.labels(status=str(response.status_code), **labels).inc()

    logger.info(
        "http_request_completed",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round(elapsed * 1000, 2),
        },
    )
    return response


# Global Exception Handler
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    correlation_id = (
        request.headers.get("X-Correlation-Id")
        or request.headers.get("X-Correlation-ID")
        or correlation_id_var.get()
    )
    if correlation_id == "<not-set>":
        correlation_id = generate_correlation_id(SERVICE_PREFIX)
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
