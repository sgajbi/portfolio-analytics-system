# libs/portfolio-common/portfolio_common/outbox_dispatcher.py
import logging
import asyncio
import json
from datetime import datetime, timezone
import functools

from sqlalchemy import update
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
    It runs its blocking I/O in a separate thread to avoid stalling the asyncio event loop.
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

    def _process_batch_sync(self):
        """
        This is a synchronous, blocking method that performs the entire outbox
        processing cycle. It is designed to be run in a thread pool executor.
        """
        events_to_process = []
        try:
            with self._session_factory() as db:
                with db.begin():
                    events_to_process = (
                        db.query(OutboxEvent)
                        .filter(OutboxEvent.status == 'PENDING')
                        .order_by(OutboxEvent.created_at)
                        .limit(BATCH_SIZE)
                        .with_for_update(skip_locked=True)
                        .all()
                    )
                    if not events_to_process:
                        return
                    # Detach events to release the lock quickly
                    for event in events_to_process:
                        db.expunge(event)
        except Exception:
            logger.error("OutboxDispatcher: Failed to fetch batch from database.", exc_info=True)
            return

        if not events_to_process:
            return

        logger.info(f"OutboxDispatcher: Found {len(events_to_process)} pending events to dispatch.")
        
        processed_ids = []
        for event in events_to_process:
            try:
                headers = [('correlation_id', event.correlation_id.encode('utf-8'))] if event.correlation_id else []
                payload_dict = json.loads(event.payload)
                self._producer.publish_message(
                    topic=event.topic,
                    key=event.aggregate_id,
                    value=payload_dict,
                    headers=headers
                )
                processed_ids.append(event.id)
            except Exception:
                logger.error(f"OutboxDispatcher: Failed to stage event {event.id} for Kafka.", exc_info=True)

        if not processed_ids:
            return

        try:
            self._producer.flush(timeout=10)
            logger.info(f"OutboxDispatcher: Successfully flushed {len(processed_ids)} events to Kafka.")
            with self._session_factory() as db:
                with db.begin():
                    db.execute(
                        update(OutboxEvent)
                        .where(OutboxEvent.id.in_(processed_ids))
                        .values(status='PROCESSED', processed_at=datetime.now(timezone.utc))
                    )
                    logger.info(f"OutboxDispatcher: Marked {len(processed_ids)} events as PROCESSED in DB.")
        except Exception:
            logger.critical(f"OutboxDispatcher: CRITICAL - Flushed messages to Kafka but failed to update database status for IDs {processed_ids}.", exc_info=True)

    async def run(self):
        """The main async loop for the dispatcher task."""
        logger.info(f"Outbox dispatcher started. Polling every {self._poll_interval} seconds.")
        loop = asyncio.get_running_loop()
        
        while self._running:
            try:
                # Run the entire synchronous batch processing logic in a thread pool executor
                await loop.run_in_executor(
                    None,  # Use the default executor
                    self._process_batch_sync
                )
            except Exception:
                logger.error("OutboxDispatcher: An unexpected error occurred in the dispatcher run loop.", exc_info=True)
            
            await asyncio.sleep(self._poll_interval)
        logger.info("Outbox dispatcher has stopped.")