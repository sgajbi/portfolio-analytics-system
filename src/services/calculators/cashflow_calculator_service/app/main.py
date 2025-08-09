import logging
import asyncio
from .consumer_manager import ConsumerManager
from portfolio_common.logging_utils import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

async def main():
    """
    Initializes and runs the ConsumerManager.
    """
    logger.info("Cashflow Calculation Service starting up...")
    manager = ConsumerManager()
    try:
        await manager.run()
    except Exception as e:
        logger.critical(f"Cashflow Calculation Service encountered a critical error: {e}", exc_info=True)
    finally:
        logger.info("Cashflow Calculation Service has shut down.")

if __name__ == "__main__":
    asyncio.run(main())