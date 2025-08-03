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

class OutboxDispatcher:
    """
    A dispatcher that polls the outbox_events table and publishes pending
    events to Kafka in a reliable, idempotent, and concurrent-safe manner.
    It runs its blocking I/O in a separate thread to avoid stalling the asyncio event loop.
    """

    def __init__(self, kafka_producer: KafkaProducer, poll_interval: int = 5, batch_size: int = 50):
        self._producer = kafka_producer
        self._poll_interval = poll_interval
        self._batch_size = batch_size # <-- ADDED
        self._running = True
        self._session_factory = SessionLocal

    def stop(self):
        """Signals the dispatcher to gracefully shut down."""
        logger.info("Outbox dispatcher shutdown signal received.")
        self._running = False

    def _process_batch_sync(self):
        """
        This is a synchronous, blocking method that performs the entire outbox
        processing cycle within a single atomic database transaction.
        """
        try:
            with self._session_factory() as db:
                with db.begin(): # Starts a single transaction
                    # 1. Lock and fetch a batch of pending events
                    events_to_process = (
                        db.query(OutboxEvent)
                        .filter(OutboxEvent.status == 'PENDING')
                        .order_by(OutboxEvent.created_at)
                        .limit(self._batch_size) # <-- UPDATED
                        .with_for_update(skip_locked=True)
                        .all()
                    )

                    if not events_to_process:
                        return # No work to do

                    processed_ids = [e.id for e in events_to_process]
                    logger.info(f"OutboxDispatcher: Found {len(events_to_process)} pending events to dispatch.")

                    # 2. Stage messages for publishing
                    for event in events_to_process:
                        headers = [('correlation_id', event.correlation_id.encode('utf-8'))] if event.correlation_id else []
                        payload_dict = json.loads(event.payload) 
                        self._producer.publish_message(
                            topic=event.topic,
                            key=event.aggregate_id,
                            value=payload_dict,
                            headers=headers
                        )

                    # 3. Attempt to publish. If this fails, the transaction rolls back.
                    self._producer.flush(timeout=10)
                    logger.info(f"OutboxDispatcher: Successfully flushed {len(processed_ids)} events to Kafka.")

                    # 4. If publishing succeeds, update the events to PROCESSED
                    db.execute(
                        update(OutboxEvent)
                        .where(OutboxEvent.id.in_(processed_ids))
                        .values(status='PROCESSED', processed_at=datetime.now(timezone.utc))
                    )
                    logger.info(f"OutboxDispatcher: Marked {len(processed_ids)} events as PROCESSED in DB.")
                # 5. The transaction commits here if all steps succeeded
        except Exception as e:
            logger.error(
                "OutboxDispatcher: Failed to process batch. Transaction will be rolled back.", 
                exc_info=True
            )
            raise

    async def run(self):
        """The main async loop for the dispatcher task."""
        logger.info(f"Outbox dispatcher started. Polling every {self._poll_interval} seconds.")
        loop = asyncio.get_running_loop()
        
        while self._running:
            try:
                await loop.run_in_executor(None, self._process_batch_sync)
            except Exception:
                logger.warning("Continuing to poll after a failed batch attempt.")
            
            await asyncio.sleep(self._poll_interval)
        logger.info("Outbox dispatcher has stopped.")