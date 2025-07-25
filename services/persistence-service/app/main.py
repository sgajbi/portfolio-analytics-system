# services/persistence-service/app/main.py
import logging
import asyncio
from .consumer_manager import ConsumerManager # <-- MODIFIED: Changed to relative import

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
    logger.info("Persistence Service starting up...")
    manager = ConsumerManager()
    try:
        await manager.run()
    except Exception as e:
        logger.critical(f"Persistence Service encountered a critical error: {e}", exc_info=True)
    finally:
        logger.info("Persistence Service has shut down.")

if __name__ == "__main__":
    asyncio.run(main())