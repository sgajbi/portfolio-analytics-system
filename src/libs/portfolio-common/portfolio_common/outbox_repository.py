import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from portfolio_common.database_models import OutboxEvent
from portfolio_common.db import SessionLocal

logger = logging.getLogger(__name__)


class OutboxRepository:
    """
    Repository for creating and fetching OutboxEvent records.
    Stores payloads as native dicts so SQLAlchemy can serialize to JSON.
    """

    def __init__(self, session_factory=SessionLocal):
        self._session_factory = session_factory

    async def create_outbox_event(
        self,
        *,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        payload: Dict[str, Any],
        topic: str,
        correlation_id: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> OutboxEvent:
        """
        Create a new outbox event in PENDING status.
        - aggregate_id MUST be present (typically portfolio_id for partition affinity).
        - payload MUST be a dict; it will be stored directly in the JSON column.
        """
        if not aggregate_id:
            raise ValueError("aggregate_id (portfolio_id) is required for outbox events")

        if not isinstance(payload, dict):
            raise TypeError("payload must be a dict (will be serialized by SQLAlchemy JSON type)")

        owns_session = db is None
        if owns_session:
            db = self._session_factory()

        try:
            event = OutboxEvent(
                aggregate_type=aggregate_type,
                aggregate_id=str(aggregate_id),
                status="PENDING",
                event_type=event_type,
                payload=payload,  # store as dict; let SQLAlchemy handle JSON serialization
                topic=topic,
                correlation_id=correlation_id,
                created_at=datetime.now(timezone.utc),
            )
            db.add(event)
            await db.flush()  # ensure event.id is populated for callers in the same tx
            logger.info(
                "Outbox event created",
                extra={
                    "aggregate_type": aggregate_type,
                    "aggregate_id": aggregate_id,
                    "event_type": event_type,
                    "topic": topic,
                    "outbox_id": event.id,
                },
            )
            return event
        finally:
            if owns_session:
                db.close()