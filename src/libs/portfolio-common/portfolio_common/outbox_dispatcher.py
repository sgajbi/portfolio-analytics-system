# src/libs/portfolio-common/portfolio_common/outbox_dispatcher.py
import logging
import asyncio
import json
from datetime import datetime, timezone
from typing import Dict, List

from sqlalchemy import update, func
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

    def _process_batch_sync(self):
        """
        One outbox processing cycle:
        - track backlog gauge
        - lock & fetch a batch (SKIP LOCKED)
        - publish each event
        - wait for delivery
        - mark successes PROCESSED; failures stay PENDING with retry_count++
        - emit counters by aggregate_type/topic
        """
        with self._session_factory() as db:
            # Backlog gauge (total pending in table)
            pending_total = db.query(func.count(OutboxEvent.id)).filter(OutboxEvent.status == "PENDING").scalar() or 0
            set_outbox_pending(int(pending_total))

            with outbox_batch_timer():
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
                            if _outbox_id is None:
                                return
                            try:
                                oid = int(_outbox_id)
                            except Exception:
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

                        # payload is JSON column; should already be a dict.
                        payload_obj = event.payload
                        if isinstance(payload_obj, str):
                            # Backward-compat for any rows inserted before this change.
                            try:
                                payload_obj = json.loads(payload_obj)
                            except Exception:
                                logger.exception(
                                    "Invalid JSON payload string in outbox; leaving event for retry",
                                    extra={"outbox_id": event.id},
                                )
                                # mark this one as failed immediately
                                delivery_ack[event.id] = False
                                delivery_errs[event.id] = "invalid JSON payload"
                                continue

                        self._producer.publish_message(
                            topic=event.topic,
                            key=event.aggregate_id,  # partition affinity by aggregate (e.g., portfolio_id)
                            value=payload_obj,
                            headers=headers,
                            outbox_id=str(event.id),
                            on_delivery=_make_on_delivery(event.id),
                        )

                    self._producer.flush(timeout=10)
                    logger.info(f"OutboxDispatcher: Flush complete for {len(events_to_process)} events.")

                    success_ids = [oid for oid, ok in delivery_ack.items() if ok]
                    failure_ids = [oid for oid, ok in delivery_ack.items() if not ok]

                    # Update DB: mark successes as PROCESSED
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
                        # Metrics per failed/retired event
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
