# libs/portfolio-common/portfolio_common/outbox_dispatcher.py
import logging
import asyncio
import json
from datetime import datetime, timezone
from typing import Dict, List

from sqlalchemy import update
from portfolio_common.kafka_utils import KafkaProducer
from portfolio_common.database_models import OutboxEvent
from portfolio_common.db import SessionLocal

logger = logging.getLogger(__name__)

MAX_RETRIES = 3  # (kept for future use)
BASE_RETRY_DELAY = 2  # seconds (kept for future use)


class OutboxDispatcher:
    """
    Polls the outbox_events table and publishes PENDING events to Kafka.
    Now tracks per-message delivery results and only marks successful ones as PROCESSED.
    Failed deliveries remain PENDING with retry_count incremented, avoiding silent loss.
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
        Performs one outbox processing cycle within a single DB transaction
        to lock and fetch a batch with SKIP LOCKED. It then publishes each
        event and awaits delivery (via flush), updates DB statuses based on
        per-message delivery outcome.
        """
        with self._session_factory() as db:
            with db.begin():
                events_to_process: List[OutboxEvent] = (
                    db.query(OutboxEvent)
                    .filter(OutboxEvent.status == "PENDING")
                    .order_by(OutboxEvent.created_at)
                    .limit(self._batch_size)
                    .with_for_update(skip_locked=True)
                    .all()
                )

                if not events_to_process:
                    return

                logger.info(f"OutboxDispatcher: Found {len(events_to_process)} pending events to dispatch.")

                # Track outcomes per outbox row id. Default to failure (False) until success callback flips it.
                delivery_ack: Dict[int, bool] = {e.id: False for e in events_to_process}
                delivery_errs: Dict[int, str] = {}

                def _make_on_delivery(outbox_id: int):
                    def _on_delivery(_outbox_id: str, success: bool, error: str | None):
                        # Defensive: ignore callback if it's about a different id (should not happen)
                        if _outbox_id is None:
                            return
                        try:
                            oid = int(_outbox_id)
                        except Exception:
                            # If producer returned non-int id, we can’t map it; leave as failed.
                            return
                        if success:
                            delivery_ack[oid] = True
                        else:
                            delivery_ack[oid] = False
                            if error:
                                delivery_errs[oid] = error
                    return _on_delivery

                # Publish all messages in the batch
                for event in events_to_process:
                    headers = []
                    if event.correlation_id:
                        headers.append(("correlation_id", event.correlation_id.encode("utf-8")))

                    # event.payload is stored as a JSON string in DB
                    payload_dict = json.loads(event.payload)

                    self._producer.publish_message(
                        topic=event.topic,
                        key=event.aggregate_id,  # portfolio-scoped keying flows through to Kafka
                        value=payload_dict,
                        headers=headers,
                        # New contextual tracing for delivery results:
                        outbox_id=str(event.id),
                        on_delivery=_make_on_delivery(event.id),
                    )

                # Block until all in-flight produce callbacks are delivered.
                self._producer.flush(timeout=10)
                logger.info(f"OutboxDispatcher: Flush complete for {len(events_to_process)} events.")

                # Partition the batch into successes vs failures based on delivery callbacks
                success_ids = [oid for oid, ok in delivery_ack.items() if ok]
                failure_ids = [oid for oid, ok in delivery_ack.items() if not ok]

                # Update DB: mark successes as PROCESSED
                if success_ids:
                    db.execute(
                        update(OutboxEvent)
                        .where(OutboxEvent.id.in_(success_ids))
                        .values(status="PROCESSED", processed_at=datetime.now(timezone.utc))
                    )
                    logger.info(f"OutboxDispatcher: Marked {len(success_ids)} events as PROCESSED in DB.")

                # Update DB: failures remain PENDING; bump retry_count and last_attempted_at
                if failure_ids:
                    db.execute(
                        update(OutboxEvent)
                        .where(OutboxEvent.id.in_(failure_ids))
                        .values(
                            retry_count=OutboxEvent.retry_count + 1,
                            last_attempted_at=datetime.now(timezone.utc),
                        )
                    )
                    # Log reasons at warning level (safe; payload is not logged)
                    for fid in failure_ids:
                        reason = delivery_errs.get(fid, "unknown error")
                        logger.warning(
                            "OutboxDispatcher: Kafka delivery failed; will retry later.",
                            extra={"outbox_id": fid, "reason": reason},
                        )

    async def run(self):
        """Main async loop with simple polling; errors are logged and loop continues."""
        logger.info(f"Outbox dispatcher started. Polling every {self._poll_interval} seconds.")
        loop = asyncio.get_running_loop()

        while self._running:
            try:
                await loop.run_in_executor(None, self._process_batch_sync)
            except Exception:
                logger.error(
                    "Failed to process outbox batch. This is now handled by the main polling loop.",
                    exc_info=True,
                )

            try:
                await asyncio.sleep(self._poll_interval)
            except asyncio.CancelledError:
                break
        logger.info("Outbox dispatcher has stopped.")
