import logging
import asyncio
from app.consumer_manager import ConsumerManager

# Configure logging for the service
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
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