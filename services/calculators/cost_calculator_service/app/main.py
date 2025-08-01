# services/cost-calculator-service/app/main.py
import logging
from app.consumer import CostCalculatorConsumer
from portfolio_common.config import KAFKA_BOOTSTRAP_SERVERS, KAFKA_RAW_TRANSACTIONS_COMPLETED_TOPIC
from portfolio_common.logging_utils import setup_logger

SERVICE_NAME = "cost-calculator-service"
logger = setup_logger(SERVICE_NAME)

def main():
    logger.info("Cost Calculator Service starting up...")
    try:
        consumer = CostCalculatorConsumer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            topic=KAFKA_RAW_TRANSACTIONS_COMPLETED_TOPIC,
            group_id="cost_calculator_group",
            service_prefix="COST"
        )
        consumer.start_consuming()
    except Exception as e:
        logger.critical(f"Cost Calculator Service failed to start: {e}", exc_info=True)
    finally:
        logger.info("Cost Calculator Service shutting down.")

if __name__ == "__main__":
    main()