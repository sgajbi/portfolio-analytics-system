# services/query-service/app/main.py
import logging
import asyncio
from fastapi import FastAPI, Request, status, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import text
from portfolio_common.logging_utils import setup_logging, correlation_id_var, generate_correlation_id
from portfolio_common.db import get_db_session
from .routers import positions, transactions, instruments, prices, fx_rates, portfolios

SERVICE_PREFIX = "QRY"
setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Query Service",
    description="Service for querying portfolio analytics data.",
    version="0.2.0"
)

@app.middleware("http")
async def add_correlation_id_middleware(request: Request, call_next):
    """
    Checks for an existing correlation ID in the request header or generates
    a new one. It sets this ID in the context for logging purposes.
    """
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
    This middleware will log the full traceback for any unhandled exception
    that occurs in the application, which is critical for debugging 500 errors.
    It now returns a generic error message to the client, including the correlation ID for traceability.
    """
    correlation_id = correlation_id_var.get()
    logger.critical(
        f"Unhandled exception for request {request.method} {request.url}",
        exc_info=exc, # This ensures the full stack trace is logged
        extra={"correlation_id": correlation_id}
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal Server Error",
            "message": "An unexpected error occurred. Please contact support.",
            "correlation_id": correlation_id # Provide ID for tracing
        },
    )

# --- Health Probe Logic ---

async def check_db_health():
    """Checks if a valid connection can be established with the database."""
    try:
        with next(get_db_session()) as db:
            # Run the synchronous DB call in a separate thread to avoid blocking the event loop
            await asyncio.to_thread(db.execute, text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Health Check: Database connection failed: {e}", exc_info=True)
        return False

@app.get("/health/live", status_code=status.HTTP_200_OK, tags=["Health"])
async def liveness_probe():
    """
    Liveness probe: A simple check to confirm the service process is running and responsive.
    """
    logger.info("Liveness probe was called.")
    return {"status": "alive"}

@app.get("/health/ready", status_code=status.HTTP_200_OK, tags=["Health"])
async def readiness_probe():
    """
    Readiness probe: Checks if the service can connect to its dependencies (PostgreSQL)
    and is ready to process requests.
    """
    logger.info("Readiness probe was called.")
    db_ok = await check_db_health()

    if db_ok:
        return {"status": "ready", "dependencies": {"database": "ok"}}
    
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "status": "not_ready",
            "dependencies": {
                "database": "ok" if db_ok else "unavailable",
            },
        },
    )

# --- NEW: Temporary Debug Endpoint ---
@app.get("/debug-error", tags=["Debug"])
async def trigger_error():
    """
    A temporary endpoint for testing the global exception handler.
    This will be removed before final production deployment.
    """
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