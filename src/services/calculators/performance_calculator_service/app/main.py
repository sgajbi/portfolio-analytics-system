# src/services/calculators/performance_calculator_service/app/main.py
import logging
import asyncio
from portfolio_common.logging_utils import setup_logging
from prometheus_fastapi_instrumentator import Instrumentator
from .web import app as web_app

setup_logging()
logger = logging.getLogger(__name__)


async def main():
    """
    Initializes and runs the Performance Calculator Service.
    For now, it only starts the web server for health probes.
    """
    logger.info("Performance Calculator Service starting up...")

    Instrumentator().instrument(web_app).expose(web_app)
    logger.info("Prometheus metrics exposed at /metrics")

    # ConsumerManager will be added in a future step
    # manager = ConsumerManager()
    try:
        # await manager.run() # This will be uncommented later
        # For now, we need to keep the service alive after starting the web server.
        # This will be replaced by the manager's run loop.
        await asyncio.Event().wait()
    except Exception as e:
        logger.critical(f"Performance Calculator Service encountered a critical error: {e}", exc_info=True)
    finally:
        logger.info("Performance Calculator Service has shut down.")


if __name__ == "__main__":
    # In a later step, the Uvicorn server will be started by the ConsumerManager.
    # For now, we don't run anything here to avoid complexity.
    # The CMD in the Dockerfile will start the `main` module.
    asyncio.run(main())