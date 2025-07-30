# services/persistence-service/app/main.py
import logging
import asyncio
import sys
import structlog
from pythonjsonlogger import jsonlogger

# Import the correlation ID context variable from the shared library
from portfolio_common.kafka_consumer import correlation_id_cv
from .consumer_manager import ConsumerManager

def configure_logging():
    """
    Configures structured logging for the service.
    """
    # Define a processor to add the correlation ID from our context variable
    def add_correlation_id(logger, method_name, event_dict):
        correlation_id = correlation_id_cv.get()
        if correlation_id:
            event_dict['correlation_id'] = correlation_id
        return event_dict

    logging.basicConfig(handlers=[logging.StreamHandler(sys.stdout)], level=logging.INFO, format="%(message)s")

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            add_correlation_id,
            structlog.stdlib.render_to_log_kwargs,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    handler = logging.StreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter()
    handler.setFormatter(formatter)
    
    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(logging.INFO)

# Use the new logger
logger = structlog.get_logger(__name__)

async def main():
    """
    Initializes and runs the ConsumerManager.
    """
    # Configure logging on startup
    configure_logging()

    logger.info("Persistence Service starting up...")
    manager = ConsumerManager()
    try:
        await manager.run()
    except Exception as e:
        logger.critical("Persistence Service encountered a critical error", error=str(e), exc_info=True)
    finally:
        logger.info("Persistence Service has shut down.")

if __name__ == "__main__":
    asyncio.run(main())