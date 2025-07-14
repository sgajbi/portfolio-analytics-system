import logging
from app.consumers.transaction_cost_consumer import TransactionCostConsumer
from common.config import KAFKA_BOOTSTRAP_SERVERS
from common.events import KAFKA_RAW_TRANSACTIONS_COMPLETED_TOPIC # Import the correct topic

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    logger.info("Transaction Cost Calculator Service starting up...")
    consumer = TransactionCostConsumer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        topic=KAFKA_RAW_TRANSACTIONS_COMPLETED_TOPIC
    )
    try:
        logger.info("Transaction Cost Consumer initialized successfully.")
        consumer.start_consuming()
    except Exception as e:
        logger.error(f"Transaction Cost Calculator Service failed to start: {e}", exc_info=True)