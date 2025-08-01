# libs/portfolio-common/portfolio_common/idempotency_repository.py
import logging
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import exists

from .database_models import ProcessedEvent

logger = logging.getLogger(__name__)

class IdempotencyRepository:
    """
    Handles all database interactions for ensuring idempotency via the
    processed_events table.
    """
    def __init__(self, db: Session):
        """
        Initializes the repository with a database session.
        Args:
            db: The SQLAlchemy Session to use for database operations.
        """
        self.db = db

    def is_event_processed(self, event_id: str, service_name: str) -> bool:
        """
        Checks if an event has already been processed by a specific service.
        Args:
            event_id: The unique identifier of the event.
            service_name: The name of the service processing the event.

        Returns:
            True if the event has been processed, False otherwise.
        """
        query = self.db.query(
            exists().where(
                ProcessedEvent.event_id == event_id,
                ProcessedEvent.service_name == service_name
            )
        )
        return self.db.scalar(query)

    def mark_event_processed(
        self,
        event_id: str,
        portfolio_id: str,
        service_name: str,
        correlation_id: Optional[str] = None
    ) -> None:
        """
        Marks an event as processed by inserting its details into the
        processed_events table.

        Args:
            event_id: The unique identifier of the event.
            portfolio_id: The portfolio ID associated with the event.
            service_name: The name of the service that processed the event.
            correlation_id: The correlation ID for tracing the event flow.
        """
        processed_event = ProcessedEvent(
            event_id=event_id,
            portfolio_id=portfolio_id,
            service_name=service_name,
            correlation_id=correlation_id # NEW: Set the correlation_id
        )
        self.db.add(processed_event)
        logger.debug(
            f"Event {event_id} marked as processed for service {service_name}",
            extra={"event_id": event_id, "service_name": service_name, "correlation_id": correlation_id}
        )