# libs/portfolio-common/portfolio_common/logging_utils.py
import logging
import sys
import uuid
from contextvars import ContextVar

# This shared context variable will hold the correlation ID for each request/event.
# It's initialized with a default value for cases where it's not explicitly set.
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="<not-set>")

class CorrelationIdFilter(logging.Filter):
    """
    A logging filter that injects the current correlation ID from a ContextVar
    into the log record.
    """
    def filter(self, record):
        """
        Attaches the correlation ID to the log record.

        Args:
            record: The log record to be filtered.

        Returns:
            True to allow the record to be processed.
        """
        record.correlation_id = correlation_id_var.get()
        return True

def setup_logger(service_name: str) -> logging.Logger:
    """
    Configures and returns a standardized logger for a given service.

    Args:
        service_name: The name of the service (e.g., 'ingestion-service').

    Returns:
        A configured Logger instance.
    """
    logger = logging.getLogger(service_name)
    
    # Prevent duplicate handlers if the function is called multiple times
    if logger.hasHandlers():
        logger.handlers.clear()
        
    logger.setLevel(logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    
    # Define a standard format that includes the correlation ID
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] [corr_id=%(correlation_id)s] [%(name)s] - %(message)s"
    )
    
    handler.setFormatter(formatter)
    
    # Add our custom filter to the handler
    handler.addFilter(CorrelationIdFilter())

    logger.addHandler(handler)
    
    # Prevent the log from propagating to the root logger
    logger.propagate = False
    
    return logger

def generate_correlation_id(prefix: str) -> str:
    """
    Generates a new correlation ID with a service-specific prefix.
    
    Args:
        prefix: A short code for the service (e.g., 'ING').

    Returns:
        A formatted correlation ID string.
    """
    return f"{prefix}:{uuid.uuid4()}"