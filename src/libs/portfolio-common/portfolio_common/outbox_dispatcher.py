# src/libs/portfolio-common/portfolio_common/outbox_dispatcher.py
import logging
import asyncio
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy import update, func
from sqlalchemy.orm import Session, sessionmaker

from portfolio_common.kafka_utils import KafkaProducer, get_kafka_producer
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

    def __init__(self, kafka_producer: KafkaProducer, poll_interval: int = 5, batch_size: int = 50, db_session_factory: Optional[sessionmaker] = None):
        self._producer = kafka_producer
        self._poll_interval = poll_interval
        self._batch_size = batch_size
        self._running = True
        self._session_factory = db_session_factory or SessionLocal

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
        self._read_pending_gauge()

        with self._session_factory() as db:  # type: Session
            with outbox_batch_timer():
                with db.begin():
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
                        def _cb(replayed_outbox_id: str, success: bool, error_message: Optional[str]):
                            if success:
                                delivery_ack[outbox_id] = True
                            else:
                                delivery_ack[outbox_id] = False
                                delivery_errs[outbox_id] = str(error_message)
                        return _cb

                    for event in events_to_process:
                        headers = []
                        if event.correlation_id:
                            headers.append(("correlation_id", event.correlation_id.encode("utf-8")))

                        payload_obj = event.payload if isinstance(event.payload, dict) else json.loads(event.payload)

                        self._producer.publish_message(
                            topic=event.topic,
                            key=event.aggregate_id,
                            value=payload_obj,
                            headers=headers,
                            outbox_id=str(event.id),
                            on_delivery=_make_on_delivery(event.id),
                        )
                    
                    try:
                        self._producer.flush(timeout=10)
                        logger.info(f"OutboxDispatcher: Flush complete for {len(events_to_process)} events.")
                    except Exception as e:
                        logger.error("OutboxDispatcher: Kafka flush failed.", exc_info=True)
                        for event in events_to_process:
                            if event.id not in delivery_ack:
                                delivery_ack[event.id] = False
                                delivery_errs[event.id] = str(e)

                    success_ids = [oid for oid, ok in delivery_ack.items() if ok]
                    failure_ids = [oid for oid, ok in delivery_ack.items() if not ok]

                    if success_ids:
                        db.execute(
                            update(OutboxEvent)
                            .where(OutboxEvent.id.in_(success_ids))
                            .values(status="PROCESSED", processed_at=datetime.now(timezone.utc))
                        )
                        for e in events_to_process:
                            if e.id in success_ids:
                                observe_outbox_published(e.aggregate_type, e.topic)
                        logger.info(f"OutboxDispatcher: Marked {len(success_ids)} events as PROCESSED in DB.")

                    if failure_ids:
                        db.execute(
                            update(OutboxEvent)
                            .where(OutboxEvent.id.in_(failure_ids))
                            .values(
                                retry_count=func.coalesce(OutboxEvent.retry_count, 0) + 1,
                                last_attempted_at=datetime.now(timezone.utc),
                            )
                        )
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
        
        while self._running:
            try:
                await asyncio.to_thread(self._process_batch_sync)
            except Exception:
                logger.error("Failed to process outbox batch.", exc_info=True)

            try:
                await asyncio.sleep(self._poll_interval)
            except asyncio.CancelledError:
                break
        
        logger.info("Outbox dispatcher has stopped.")