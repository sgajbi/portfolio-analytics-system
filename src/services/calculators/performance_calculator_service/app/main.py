# src/services/calculators/performance_calculator_service/app/main.py
import logging
from prometheus_fastapi_instrumentator import Instrumentator
from portfolio_common.logging_utils import setup_logging
from .web import app

setup_logging()
logger = logging.getLogger(__name__)

logger.info("Performance Calculator Service starting up...")

Instrumentator().instrument(app).expose(app)
logger.info("Prometheus metrics exposed at /metrics")

# The app object is now the main export. Uvicorn will run this.
# The ConsumerManager and its logic will be added in a future step.