# services/timeseries-generator-service/app/main.py
import logging
import asyncio
from .consumer_manager import ConsumerManager
from portfolio_common.logging_utils import setup_logger

SERVICE_NAME = "timeseries-generator-service"
logger = setup_logger(SERVICE_NAME)

async def main():
    """
    Initializes and runs the ConsumerManager.
    """
    logger.info("Time Series Generator Service starting up...")
    manager = ConsumerManager()
    try:
        await manager.run()
    except Exception as e:
        logger.critical(f"Time Series Generator Service encountered a critical error: {e}", exc_info=True)
    finally:
        logger.info("Time Series Generator Service has shut down.")

if __name__ == "__main__":
    asyncio.run(main())