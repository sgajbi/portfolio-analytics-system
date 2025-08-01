# services/calculators/cashflow_calculator_service/app/main.py
import logging
import asyncio
from .consumer_manager import ConsumerManager
from portfolio_common.logging_utils import setup_logger

SERVICE_NAME = "cashflow-calculator-service"
logger = setup_logger(SERVICE_NAME)

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