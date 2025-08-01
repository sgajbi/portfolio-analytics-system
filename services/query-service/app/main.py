# services/query-service/app/main.py
import logging
from fastapi import FastAPI, Request
from portfolio_common.logging_utils import setup_logging, correlation_id_var, generate_correlation_id
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

# Register the API routers
app.include_router(portfolios.router)
app.include_router(positions.router)
app.include_router(transactions.router)
app.include_router(instruments.router)
app.include_router(prices.router)
app.include_router(fx_rates.router)

@app.get("/health")
async def health_check():
    """Returns the operational status of the service."""
    logger.info("Health check endpoint was called.")
    return {"status": "ok", "service": "Query Service"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)