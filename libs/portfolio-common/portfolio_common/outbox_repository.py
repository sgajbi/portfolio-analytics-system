# libs/portfolio-common/portfolio_common/outbox_repository.py
import logging
from sqlalchemy.orm import Session
from typing import Dict, Any

from .database_models import OutboxEvent

logger = logging.getLogger(__name__)

class OutboxRepository:
    """
    Handles database operations for creating OutboxEvent records.
    This repository is responsible for staging the event in the database session,
    but it does NOT commit the transaction.
    """

    def create_outbox_event(
        self,
        db_session: Session,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        topic: str,
        payload: Dict[str, Any],
    ) -> OutboxEvent:
        """
        Creates an OutboxEvent instance and adds it to the provided database session.

        Args:
            db_session: The SQLAlchemy Session for the current transaction.
            aggregate_type: The type of the domain entity (e.g., 'Transaction', 'Cashflow').
            aggregate_id: The unique identifier of the entity instance.
            event_type: The specific type of the event (e.g., 'TransactionPersisted').
            topic: The Kafka topic to which this event should be published.
            payload: The JSON-serializable event payload.

        Returns:
            The created OutboxEvent instance.
        """
        try:
            outbox_event = OutboxEvent(
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                event_type=event_type,
                topic=topic,
                payload=payload,
                status='PENDING'
            )
            db_session.add(outbox_event)
            logger.info(
                "Staged new outbox event for publishing.",
                extra={
                    "topic": topic,
                    "aggregate_id": aggregate_id,
                    "event_type": event_type,
                },
            )
            return outbox_event
        except Exception as e:
            logger.error(
                "Failed to stage outbox event.",
                extra={"aggregate_id": aggregate_id, "topic": topic},
                exc_info=True,
            )
            raise