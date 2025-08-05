# services/query-service/app/main.py
import logging
import asyncio
from fastapi import FastAPI, Request, status, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import text
from prometheus_fastapi_instrumentator import Instrumentator
from portfolio_common.logging_utils import setup_logging, correlation_id_var, generate_correlation_id
from portfolio_common.db import AsyncSessionLocal # <-- UPDATED IMPORT
from .routers import positions, transactions, instruments, prices, fx_rates, portfolios

SERVICE_PREFIX = "QRY"
setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Query Service",
    description="Service for querying portfolio analytics data.",
    version="0.2.0"
)

# --- Prometheus Metrics Instrumentation ---
Instrumentator().instrument(app).expose(app)
logger.info("Prometheus metrics exposed at /metrics")

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

# --- UPDATED: Async Health Probe Logic ---

async def check_db_health():
    """Checks if a valid connection can be established with the database."""
    try:
        # Use the async session factory directly for a self-contained check
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await session.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Health Check: Database connection failed: {e}", exc_info=False)
        return False

@app.get("/health/live", status_code=status.HTTP_200_OK, tags=["Health"])
async def liveness_probe():
    logger.info("Liveness probe was called.")
    return {"status": "alive"}

@app.get("/health/ready", status_code=status.HTTP_200_OK, tags=["Health"])
async def readiness_probe():
    logger.info("Readiness probe was called.")
    db_ok = await check_db_health()
    if db_ok:
        return {"status": "ready", "dependencies": {"database": "ok"}}
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={"status": "not_ready", "dependencies": {"database": "unavailable"}},
    )

# --- Temporary Debug Endpoint ---
@app.get("/debug-error", tags=["Debug"])
async def trigger_error():
    raise ValueError("This is a test exception to verify error handling.")

# Register the API routers
app.include_router(portfolios.router)
app.include_router(positions.router)
app.include_router(transactions.router)
app.include_router(instruments.router)
app.include_router(prices.router)
app.include_router(fx_rates.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)