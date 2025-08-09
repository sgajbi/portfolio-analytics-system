# src/libs/portfolio-common/portfolio_common/monitoring.py
import logging
from typing import Optional
from prometheus_client import Counter, Gauge, Histogram

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------------------
# DB metrics (used by portfolio_common.utils.async_timed, etc.)
# --------------------------------------------------------------------------------------
# NOTE: utils.async_timed expects labels (repository, method). Keep this signature stable.
DB_OPERATION_LATENCY_SECONDS = Histogram(
    "db_operation_latency_seconds",
    "Latency of database operations in seconds",
    labelnames=("repository", "method"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)

def db_timer(operation: str):
    """
    Backwards/ergonomic helper. Times a DB operation using a generic repository label.
    Usage:
        with db_timer("transaction_upsert"):
            ...
    """
    return DB_OPERATION_LATENCY_SECONDS.labels(repository="db", method=operation).time()

# --------------------------------------------------------------------------------------
# Kafka (generic) metrics – available for any service to use
# --------------------------------------------------------------------------------------
KAFKA_MESSAGES_PUBLISHED_TOTAL = Counter(
    "kafka_messages_published_total",
    "Number of messages successfully published to Kafka",
    labelnames=("topic",),
)

KAFKA_PUBLISH_ERRORS_TOTAL = Counter(
    "kafka_publish_errors_total",
    "Number of Kafka publish errors",
    labelnames=("topic", "error"),
)

KAFKA_MESSAGES_CONSUMED_TOTAL = Counter(
    "kafka_messages_consumed_total",
    "Number of messages consumed from Kafka",
    labelnames=("topic", "group_id"),
)

KAFKA_CONSUME_ERRORS_TOTAL = Counter(
    "kafka_consume_errors_total",
    "Number of Kafka consume errors",
    labelnames=("topic", "error"),
)

KAFKA_PUBLISH_LATENCY_SECONDS = Histogram(
    "kafka_publish_latency_seconds",
    "Kafka publish latency in seconds by topic",
    labelnames=("topic",),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)

def observe_kafka_published(topic: str, count: int = 1) -> None:
    KAFKA_MESSAGES_PUBLISHED_TOTAL.labels(topic).inc(count)

def observe_kafka_publish_error(topic: str, error: str, count: int = 1) -> None:
    KAFKA_PUBLISH_ERRORS_TOTAL.labels(topic, error).inc(count)

def observe_kafka_consumed(topic: str, group_id: str, count: int = 1) -> None:
    KAFKA_MESSAGES_CONSUMED_TOTAL.labels(topic, group_id).inc(count)

def observe_kafka_consume_error(topic: str, error: str, count: int = 1) -> None:
    KAFKA_CONSUME_ERRORS_TOTAL.labels(topic, error).inc(count)

def kafka_publish_timer(topic: str):
    """Context manager that observes Kafka publish latency for a topic."""
    return KAFKA_PUBLISH_LATENCY_SECONDS.labels(topic).time()

# --------------------------------------------------------------------------------------
# Outbox Dispatcher Metrics
# --------------------------------------------------------------------------------------
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
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)

def observe_outbox_published(aggregate_type: str, topic: str, count: int = 1) -> None:
    _OUTBOX_PUBLISHED.labels(aggregate_type, topic).inc(count)

def observe_outbox_failed(aggregate_type: str, topic: str, count: int = 1) -> None:
    _OUTBOX_FAILED.labels(aggregate_type, topic).inc(count)

def observe_outbox_retried(aggregate_type: str, topic: str, count: int = 1) -> None:
    _OUTBOX_RETRIED.labels(aggregate_type, topic).inc(count)

def set_outbox_pending(total_pending: int) -> None:
    _OUTBOX_PENDING.set(total_pending)

def outbox_batch_timer():
    """Context manager that observes outbox batch duration."""
    return _OUTBOX_BATCH_SECONDS.time()

# --------------------------------------------------------------------------------------
# Optional generic HTTP metrics (use across services if helpful)
# --------------------------------------------------------------------------------------
HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "HTTP requests total",
    labelnames=("service", "method", "path", "status"),
)

HTTP_REQUEST_LATENCY_SECONDS = Histogram(
    "http_request_latency_seconds",
    "HTTP request latency in seconds",
    labelnames=("service", "method", "path"),
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)

def http_request_timer(service: str, method: str, path: str):
    """Context manager for timing an HTTP request handler."""
    return HTTP_REQUEST_LATENCY_SECONDS.labels(service, method, path).time()
