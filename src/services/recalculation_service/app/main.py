# src/services/recalculation_service/app/main.py
import logging
import asyncio
from app.consumer_manager import ConsumerManager
from portfolio_common.logging_utils import setup_logging
from prometheus_fastapi_instrumentator import Instrumentator

# This import is necessary for the Instrumentator to find the web app
from .web import app as web_app

setup_logging()
logger = logging.getLogger(__name__)

async def main():
    """
    Initializes and runs the ConsumerManager for the Recalculation Service.
    """
    logger.info("Recalculation Service starting up...")
    
    Instrumentator().instrument(web_app).expose(web_app)
    logger.info("Prometheus metrics exposed at /metrics")

    manager = ConsumerManager()
    try:
        await manager.run()
    except Exception as e:
        logger.critical(f"Recalculation Service encountered a critical error: {e}", exc_info=True)
    finally:
        logger.info("Recalculation Service has shut down.")

if __name__ == "__main__":
    asyncio.run(main())