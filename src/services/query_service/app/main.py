# services/query-service/app/main.py
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from portfolio_common.logging_utils import setup_logging, correlation_id_var, generate_correlation_id
from portfolio_common.health import create_health_router
from .routers import positions, transactions, instruments, prices, fx_rates, portfolios, performance

SERVICE_PREFIX = "QRY"
setup_logging()
logger = logging.getLogger(__name__)
# ... (lifespan, middleware, and exception handler are unchanged) ...

app = FastAPI(
    title="Query Service",
    description="Service for querying portfolio analytics data.",
    version="0.2.0",
    lifespan=lifespan
)

# ... (Prometheus, middleware, exception handler are unchanged) ...

# Create and include the standardized health router.
# This service depends on the database.
health_router = create_health_router('db')
app.include_router(health_router)

# Register the API routers
app.include_router(portfolios.router)
app.include_router(positions.router)
app.include_router(transactions.router)
app.include_router(instruments.router)
app.include_router(prices.router)
app.include_router(fx_rates.router)
app.include_router(performance.router)