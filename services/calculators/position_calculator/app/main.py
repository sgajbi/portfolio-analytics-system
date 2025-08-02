
# services/calculators/position_calculator/app/main.py
import logging
import asyncio
from app.consumer_manager import ConsumerManager
from portfolio_common.logging_utils import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

async def main():
    """
    Initializes and runs the ConsumerManager.
    """
    logger.info("Position Calculation Service starting up...")
    manager = ConsumerManager()
    try:
        await manager.run()
    except Exception as e:
        logger.critical(f"Position Calculation Service encountered a critical error: {e}", exc_info=True)
    finally:
        logger.info("Position Calculation Service has shut down.")

if __name__ == "__main__":
    asyncio.run(main())