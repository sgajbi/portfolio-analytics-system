from __future__ import annotations

import os
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Annotated

from fastapi import Header, HTTPException, Request, status


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


OPS_TOKEN_REQUIRED = _as_bool(os.getenv("LOTUS_CORE_INGEST_OPS_TOKEN_REQUIRED"), True)
OPS_TOKEN_VALUE = os.getenv("LOTUS_CORE_INGEST_OPS_TOKEN", "lotus-core-ops-local")

RATE_LIMIT_ENABLED = _as_bool(os.getenv("LOTUS_CORE_INGEST_RATE_LIMIT_ENABLED"), True)
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("LOTUS_CORE_INGEST_RATE_LIMIT_WINDOW_SECONDS", "60"))
RATE_LIMIT_MAX_REQUESTS = int(os.getenv("LOTUS_CORE_INGEST_RATE_LIMIT_MAX_REQUESTS", "120"))
RATE_LIMIT_MAX_RECORDS = int(os.getenv("LOTUS_CORE_INGEST_RATE_LIMIT_MAX_RECORDS", "10000"))

OpsTokenHeader = Annotated[
    str | None,
    Header(
        alias="X-Lotus-Ops-Token",
        description=(
            "Operations token for privileged ingestion runbook APIs "
            "(health controls, retry, DLQ triage, idempotency diagnostics)."
        ),
    ),
]


@dataclass(slots=True)
class _WriteEvent:
    observed_at: datetime
    record_count: int


_write_events: dict[str, deque[_WriteEvent]] = defaultdict(deque)
_rate_limit_lock = Lock()


def _evict_expired(events: deque[_WriteEvent], now_utc: datetime) -> None:
    cutoff = now_utc - timedelta(seconds=RATE_LIMIT_WINDOW_SECONDS)
    while events and events[0].observed_at < cutoff:
        events.popleft()


def enforce_ingestion_write_rate_limit(*, endpoint: str, record_count: int) -> None:
    if not RATE_LIMIT_ENABLED:
        return
    if record_count < 1:
        record_count = 1

    now_utc = datetime.now(UTC)
    with _rate_limit_lock:
        events = _write_events[endpoint]
        _evict_expired(events, now_utc)
        current_requests = len(events)
        current_records = sum(item.record_count for item in events)
        projected_requests = current_requests + 1
        projected_records = current_records + record_count
        if (
            projected_requests > RATE_LIMIT_MAX_REQUESTS
            or projected_records > RATE_LIMIT_MAX_RECORDS
        ):
            raise PermissionError(
                "Ingestion write rate limit exceeded. "
                f"window_seconds={RATE_LIMIT_WINDOW_SECONDS}, "
                f"max_requests={RATE_LIMIT_MAX_REQUESTS}, "
                f"max_records={RATE_LIMIT_MAX_RECORDS}."
            )
        events.append(_WriteEvent(observed_at=now_utc, record_count=record_count))


async def require_ops_token(
    request: Request,
    ops_token: OpsTokenHeader = None,
) -> str:
    if not OPS_TOKEN_REQUIRED:
        return "ops-token-not-required"
    if not ops_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "INGESTION_OPS_TOKEN_REQUIRED",
                "message": (
                    "Missing X-Lotus-Ops-Token header for privileged ingestion operations API."
                ),
            },
        )
    if ops_token != OPS_TOKEN_VALUE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "INGESTION_OPS_TOKEN_INVALID",
                "message": "Invalid X-Lotus-Ops-Token.",
            },
        )
    return request.headers.get("X-Principal", "ops-token")
