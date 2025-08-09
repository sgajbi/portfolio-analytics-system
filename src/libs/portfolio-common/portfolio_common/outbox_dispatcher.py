# src/libs/portfolio-common/portfolio_common/outbox_dispatcher.py
import logging
import asyncio
import json
from datetime import datetime, timezone
from typing import Dict, List

from sqlalchemy import update, func
from sqlalchemy.orm import Session

from portfolio_common.kafka_utils import KafkaProducer
from portfolio_common.database_models import OutboxEvent
from portfolio_common.db import SessionLocal
from portfolio_common.monitoring import (
    observe_outbox_published,
    observe_outbox_failed,
    observe_outbox_retried,
    set_outbox_pending,
    outbox_batch_timer,
)

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
BASE_RETRY_DELAY = 2  # seconds


class OutboxDispatcher:
    """
    Polls the outbox_events table and publishes PENDING events to Kafka.
    Tracks per-message delivery results and only marks successful ones as PROCESSED.
    Failed deliveries remain PENDING with retry_count incremented.
    Emits Prometheus metrics for visibility.
    """

    def __init__(self, kafka_producer: KafkaProducer, poll_interval: int = 5, batch_size: int = 50):
        self._producer = kafka_producer
        self._poll_interval = poll_interval
        self._batch_size = batch_size
        self._running = True
        self._session_factory = SessionLocal

    def stop(self):
        logger.info("Outbox dispatcher shutdown signal received.")
        self._running = False

    def _read_pending_gauge(self) -> None:
        """Reads PENDING count in a short-lived session to avoid interfering with the batch tx."""
        with self._session_factory() as s:  # type: Session
            pending_total = s.query(func.count(OutboxEvent.id)).filter(OutboxEvent.status == "PENDING").scalar() or 0
            set_outbox_pending(int(pending_total))

    def _process_batch_sync(self) -> None:
        """
        Single batch:
        - Read pending gauge using a separate short-lived session (no open tx carried over)
        - Open a new session/transaction
        - SELECT ... FOR UPDATE SKIP LOCKED a slice of PENDING events
        - Publish to Kafka
        - Update statuses (PROCESSED or increment retry_count) in the same transaction
        """
        # Read gauge outside of the transactional batch to prevent auto-begin conflicts
        self._read_pending_gauge()

        with self._session_factory() as db:  # type: Session
            with outbox_batch_timer():
                # Use a single explicit transaction for the whole batch work in this session.
                with db.begin():
                    # Lock a window of PENDING events so multiple dispatchers can work concurrently.
                    events_to_process: List[OutboxEvent] = (
                        db.query(OutboxEvent)
                        .filter(OutboxEvent.status == "PENDING")
                        .order_by(OutboxEvent.created_at.asc())
                        .with_for_update(skip_locked=True, of=OutboxEvent)
                        .limit(self._batch_size)
                        .all()
                    )

                    if not events_to_process:
                        return

                    delivery_ack: Dict[int, bool] = {}
                    delivery_errs: Dict[int, str] = {}

                    def _make_on_delivery(outbox_id: int):
                        def _cb(err, _msg):
                            if err is None:
                                delivery_ack[outbox_id] = True
                            else:
                                delivery_ack[outbox_id] = False
                                delivery_errs[outbox_id] = str(err)
                        return _cb

                    # Publish all events in this batch
                    for event in events_to_process:
                        # Headers
                        headers = []
                        if event.correlation_id:
                            headers.append(("correlation_id", event.correlation_id.encode("utf-8")))

                        # Payload is stored as JSON (SQLAlchemy JSON type) or dict; ensure dict
                        payload_obj = event.payload if isinstance(event.payload, dict) else json.loads(event.payload)

                        self._producer.publish_message(
                            topic=event.topic,
                            key=event.aggregate_id,  # partition affinity by aggregate (e.g., portfolio_id)
                            value=payload_obj,
                            headers=headers,
                            outbox_id=str(event.id),
                            on_delivery=_make_on_delivery(event.id),
                        )

                    # Flush to get delivery results
                    self._producer.flush(timeout=10)
                    logger.info(f"OutboxDispatcher: Flush complete for {len(events_to_process)} events.")

                    success_ids = [oid for oid, ok in delivery_ack.items() if ok]
                    failure_ids = [oid for oid, ok in delivery_ack.items() if not ok]

                    # Mark successes as PROCESSED
                    if success_ids:
                        db.execute(
                            update(OutboxEvent)
                            .where(OutboxEvent.id.in_(success_ids))
                            .values(status="PROCESSED", processed_at=datetime.now(timezone.utc))
                        )
                        # Metrics per successful event
                        for e in events_to_process:
                            if e.id in success_ids:
                                observe_outbox_published(e.aggregate_type, e.topic)

                        logger.info(f"OutboxDispatcher: Marked {len(success_ids)} events as PROCESSED in DB.")

                    # Failures remain PENDING; bump retry_count and last_attempted_at
                    if failure_ids:
                        db.execute(
                            update(OutboxEvent)
                            .where(OutboxEvent.id.in_(failure_ids))
                            .values(
                                retry_count=OutboxEvent.retry_count + 1,
                                last_attempted_at=datetime.now(timezone.utc),
                            )
                        )
                        # Metrics per failed/retried event
                        for e in events_to_process:
                            if e.id in failure_ids:
                                observe_outbox_failed(e.aggregate_type, e.topic)
                                observe_outbox_retried(e.aggregate_type, e.topic)

                        for fid in failure_ids:
                            reason = delivery_errs.get(fid, "unknown error")
                            logger.warning(
                                "OutboxDispatcher: Kafka delivery failed; will retry later.",
                                extra={"outbox_id": fid, "reason": reason},
                            )

    async def run(self):
        logger.info(f"Outbox dispatcher started. Polling every {self._poll_interval} seconds.")
        loop = asyncio.get_running_loop()

        while self._running:
            try:
                await loop.run_in_executor(None, self._process_batch_sync)
            except Exception:
                logger.error("Failed to process outbox batch.", exc_info=True)

            try:
                await asyncio.sleep(self._poll_interval)
            except asyncio.CancelledError:
                break
        logger.info("Outbox dispatcher has stopped.")
