import logging
from app.consumers.transaction_consumer import TransactionConsumer
from portfolio_common.config import KAFKA_BOOTSTRAP_SERVERS, KAFKA_RAW_TRANSACTIONS_TOPIC # <-- CORRECTED IMPORT

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    logger.info("Transaction Persistence Service starting up...")
    try:
        # Initialize and start the Kafka consumer
        consumer = TransactionConsumer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            topic=KAFKA_RAW_TRANSACTIONS_TOPIC,
            group_id="transaction_persistence_group" # This should ideally be configurable via env vars
        )
        consumer.start_consuming()
    except Exception as e:
        logger.critical(f"Transaction Persistence Service failed to start or encountered a critical error: {e}", exc_info=True)
    finally:
        logger.info("Transaction Persistence Service shutting down.")

if __name__ == "__main__":
    main()