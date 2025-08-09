# src/libs/portfolio-common/portfolio_common/monitoring.py
import logging
from typing import Optional

from prometheus_client import Counter, Gauge, Histogram

logger = logging.getLogger(__name__)

# --- Outbox Dispatcher Metrics ---

_OUTBOX_PUBLISHED = Counter(
    "outbox_events_published_total",
    "Number of outbox events successfully published to Kafka",
    labelnames=("aggregate_type", "topic"),
)

_OUTBOX_FAILED = Counter(
    "outbox_events_failed_total",
    "Number of outbox events that failed to publish to Kafka",
    labelnames=("aggregate_type", "topic"),
)

_OUTBOX_RETRIED = Counter(
    "outbox_events_retried_total",
    "Number of outbox events marked for retry after failed publishes",
    labelnames=("aggregate_type", "topic"),
)

_OUTBOX_PENDING = Gauge(
    "outbox_events_pending",
    "Total number of PENDING outbox events in the database",
)

_OUTBOX_BATCH_SECONDS = Histogram(
    "outbox_dispatch_batch_seconds",
    "Time taken to process one outbox dispatch batch (lock, publish, update statuses).",
    buckets=(
        0.05, 0.1, 0.25, 0.5,
        1.0, 2.5, 5.0, 10.0,
        30.0, 60.0
    ),
)


def observe_outbox_published(aggregate_type: str, topic: str, count: int = 1) -> None:
    """Increment the published counter for an aggregate/topic by count."""
    _OUTBOX_PUBLISHED.labels(aggregate_type, topic).inc(count)


def observe_outbox_failed(aggregate_type: str, topic: str, count: int = 1) -> None:
    """Increment the failure counter for an aggregate/topic by count."""
    _OUTBOX_FAILED.labels(aggregate_type, topic).inc(count)


def observe_outbox_retried(aggregate_type: str, topic: str, count: int = 1) -> None:
    """Increment the retried counter for an aggregate/topic by count."""
    _OUTBOX_RETRIED.labels(aggregate_type, topic).inc(count)


def set_outbox_pending(total_pending: int) -> None:
    """Set the current number of PENDING outbox events."""
    _OUTBOX_PENDING.set(total_pending)


def outbox_batch_timer():
    """
    Context manager that observes outbox batch duration.
    Usage:
        with outbox_batch_timer():
            ... do work ...
    """
    return _OUTBOX_BATCH_SECONDS.time()
