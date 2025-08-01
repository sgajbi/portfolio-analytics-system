# services/persistence-service/app/main.py
import logging
import asyncio

from portfolio_common.logging_utils import setup_logging
from .consumer_manager import ConsumerManager

setup_logging()
logger = logging.getLogger(__name__)

async def main():
    """
    Initializes and runs the ConsumerManager.
    """
    logger.info("Persistence Service starting up...")
    manager = ConsumerManager()
    try:
        await manager.run()
    except Exception as e:
        logger.critical("Persistence Service encountered a critical error", exc_info=True)
    finally:
        logger.info("Persistence Service has shut down.")

if __name__ == "__main__":
    asyncio.run(main())