import logging
from fastapi import FastAPI
from .routers import positions, transactions, instruments, prices, fx_rates, portfolios

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Main FastAPI app instance
app = FastAPI(
    title="Query Service",
    description="Service for querying portfolio analytics data.",
    version="0.2.0" # Version bump for new feature
)

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
    return {"status": "ok", "service": "Query Service"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)