# libs/portfolio-common/portfolio_common/outbox_dispatcher.py
import logging
import asyncio
import json
from datetime import datetime, timezone
from tenacity import retry, stop_after_attempt, wait_exponential

from sqlalchemy import update
from portfolio_common.kafka_utils import KafkaProducer
from portfolio_common.database_models import OutboxEvent
from portfolio_common.db import SessionLocal

logger = logging.getLogger(__name__)


class OutboxDispatcher:
    """
    A dispatcher that polls the outbox_events table and publishes pending
    events to Kafka in a reliable, idempotent, and concurrent-safe manner.
    """

    def __init__(self, kafka_producer: KafkaProducer, poll_interval: int = 5, batch_size: int = 50):
        self._producer = kafka_producer
        self._poll_interval = poll_interval
        self._batch_size = batch_size
        self._running = True
        self._session_factory = SessionLocal

    def stop(self):
        """Signals the dispatcher to gracefully shut down."""
        logger.info("Outbox dispatcher shutdown signal received.")
        self._running = False

    def _process_batch_sync(self):
        """
        Performs the outbox processing cycle within a single atomic transaction.
        """
        try:
            with self._session_factory() as db:
                with db.begin():
                    events_to_process = (
                        db.query(OutboxEvent)
                        .filter(OutboxEvent.status == 'PENDING')
                        .order_by(OutboxEvent.created_at)
                        .limit(self._batch_size)
                        .with_for_update(skip_locked=True)
                        .all()
                    )

                    if not events_to_process:
                        return

                    processed_ids = [e.id for e in events_to_process]
                    logger.info(f"OutboxDispatcher: Found {len(events_to_process)} pending events to dispatch.")

                    for event in events_to_process:
                        headers = [('correlation_id', event.correlation_id.encode('utf-8'))] if event.correlation_id else []
                        payload_dict = json.loads(event.payload) 
                        self._producer.publish_message(
                            topic=event.topic,
                            key=event.aggregate_id,
                            value=payload_dict,
                            headers=headers
                        )

                    self._producer.flush(timeout=10)
                    logger.info(f"OutboxDispatcher: Successfully flushed {len(processed_ids)} events to Kafka.")

                    db.execute(
                        update(OutboxEvent)
                        .where(OutboxEvent.id.in_(processed_ids))
                        .values(status='PROCESSED', processed_at=datetime.now(timezone.utc))
                    )
                    logger.info(f"OutboxDispatcher: Marked {len(processed_ids)} events as PROCESSED in DB.")
        except Exception as e:
            logger.error(
                "OutboxDispatcher: Failed to process batch. Transaction will be rolled back.", 
                exc_info=True
            )
            raise

    # This decorator will handle retrying the batch processing on any exception.
    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(5)
    )
    async def _process_and_retry_batch(self):
        """Wrapper for the sync method to be used with tenacity for retries."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._process_batch_sync)

    async def run(self):
        """The main async loop for the dispatcher task."""
        logger.info(f"Outbox dispatcher started. Polling every {self._poll_interval} seconds.")
        
        while self._running:
            try:
                await self._process_and_retry_batch()
            except Exception:
                logger.critical("Outbox batch failed after all retries. Will continue polling.")
            
            # Use a non-blocking sleep to allow graceful shutdown
            try:
                await asyncio.sleep(self._poll_interval)
            except asyncio.CancelledError:
                break
        logger.info("Outbox dispatcher has stopped.")