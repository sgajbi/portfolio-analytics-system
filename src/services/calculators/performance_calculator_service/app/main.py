# src/services/calculators/performance_calculator_service/app/main.py
import logging
import asyncio
from portfolio_common.logging_utils import setup_logging
from prometheus_fastapi_instrumentator import Instrumentator
from .web import app as web_app
from .consumer_manager import ConsumerManager

setup_logging()
logger = logging.getLogger(__name__)


async def main():
    """
    Initializes and runs the Performance Calculator Service.
    """
    logger.info("Performance Calculator Service starting up...")

    Instrumentator().instrument(web_app).expose(web_app)
    logger.info("Prometheus metrics exposed at /metrics")

    manager = ConsumerManager()
    try:
        await manager.run()
    except Exception as e:
        logger.critical(f"Performance Calculator Service encountered a critical error: {e}", exc_info=True)
    finally:
        logger.info("Performance Calculator Service has shut down.")


if __name__ == "__main__":
    asyncio.run(main())