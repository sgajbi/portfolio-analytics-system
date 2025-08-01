# services/calculators/position-valuation-calculator/app/main.py
import logging
import asyncio
from app.consumer_manager import ConsumerManager
from portfolio_common.logging_utils import setup_logger

SERVICE_NAME = "position-valuation-calculator-service"
logger = setup_logger(SERVICE_NAME)

async def main():
    """
    Initializes and runs the ConsumerManager.
    """
    logger.info("Position Valuation Service starting up...")
    manager = ConsumerManager()
    try:
        await manager.run()
    except Exception as e:
        logger.critical(f"Position Valuation Service encountered a critical error: {e}", exc_info=True)
    finally:
        logger.info("Position Valuation Service has shut down.")

if __name__ == "__main__":
    asyncio.run(main())