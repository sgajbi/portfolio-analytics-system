# services/persistence-service/app/main.py
import logging
import asyncio

from portfolio_common.logging_utils import setup_logger
from .consumer_manager import ConsumerManager

SERVICE_NAME = "persistence-service"
logger = setup_logger(SERVICE_NAME) 

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