# libs/portfolio-common/portfolio_common/outbox_dispatcher.py
import logging
import asyncio
import json
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import func, update

from portfolio_common.kafka_utils import KafkaProducer
from portfolio_common.database_models import OutboxEvent
from portfolio_common.db import SessionLocal

logger = logging.getLogger(__name__)

MAX_RETRIES = 5
BATCH_SIZE = 50

class OutboxDispatcher:
    """
    A dispatcher that polls the outbox_events table and publishes pending
    events to Kafka in a reliable, idempotent, and concurrent-safe manner.
    """

    def __init__(self, kafka_producer: KafkaProducer, poll_interval: int = 5):
        self._producer = kafka_producer
        self._poll_interval = poll_interval
        self._running = True
        self._session_factory = SessionLocal

    def stop(self):
        """Signals the dispatcher to gracefully shut down."""
        logger.info("Outbox dispatcher shutdown signal received.")
        self._running = False

    async def _process_batch(self):
        """
        Fetches a batch of pending events, publishes them, and updates their status.
        Uses 'SELECT FOR UPDATE SKIP LOCKED' to prevent race conditions if multiple
        dispatcher instances are running.
        """
        events_to_process = []
        try:
            with self._session_factory() as db:
                with db.begin():
                    # Find and lock a batch of pending events
                    events_to_process = (
                        db.query(OutboxEvent)
                        .filter(OutboxEvent.status == 'PENDING')
                        .order_by(OutboxEvent.created_at)
                        .limit(BATCH_SIZE)
                        .with_for_update(skip_locked=True)
                        .all()
                    )

                    if not events_to_process:
                        return # Nothing to do

                    # Detach events from the session so we can update them later
                    # in a new session if needed, without transaction conflicts.
                    for event in events_to_process:
                        db.expunge(event)
        except Exception as e:
            logger.error("OutboxDispatcher: Failed to fetch batch from database.", exc_info=True)
            return # Abort this cycle

        logger.info(f"OutboxDispatcher: Found {len(events_to_process)} pending events to dispatch.")
        
        processed_ids = []
        
        for event in events_to_process:
            try:
                headers = []
                if event.correlation_id:
                    headers.append(('correlation_id', event.correlation_id.encode('utf-8')))
                
                # The payload is now guaranteed to be a JSON string, so we load it.
                payload_dict = json.loads(event.payload)

                self._producer.publish_message(
                    topic=event.topic,
                    key=event.aggregate_id,
                    value=payload_dict,
                    headers=headers
                )
                processed_ids.append(event.id)
            except Exception:
                logger.error(f"OutboxDispatcher: Failed to publish event {event.id} to Kafka.", exc_info=True)
                # In a real scenario, we would add retry/failure logic here.
                # For now, we will leave it to be picked up in the next poll.
        
        # Flush all messages to Kafka before updating the database
        if processed_ids:
            try:
                self._producer.flush(timeout=10)
                logger.info(f"OutboxDispatcher: Successfully flushed {len(processed_ids)} events to Kafka.")

                # Update status for successfully processed events
                with self._session_factory() as db:
                    with db.begin():
                        db.execute(
                            update(OutboxEvent)
                            .where(OutboxEvent.id.in_(processed_ids))
                            .values(status='PROCESSED', processed_at=datetime.now(timezone.utc))
                        )
                        logger.info(f"OutboxDispatcher: Marked {len(processed_ids)} events as PROCESSED in DB.")
            except Exception:
                logger.error(f"OutboxDispatcher: CRITICAL - Flushed messages to Kafka but failed to update database status for IDs {processed_ids}.", exc_info=True)


    async def run(self):
        """The main loop for the dispatcher task."""
        logger.info(f"Outbox dispatcher started. Polling every {self._poll_interval} seconds.")
        while self._running:
            await self._process_batch()
            await asyncio.sleep(self._poll_interval)
        logger.info("Outbox dispatcher has stopped.")