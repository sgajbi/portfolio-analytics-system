from typing import Annotated
from uuid import uuid4

from fastapi import Header, Request
from portfolio_common.logging_utils import correlation_id_var, request_id_var, trace_id_var


def resolve_idempotency_key(request: Request) -> str | None:
    return request.headers.get("X-Idempotency-Key")


IdempotencyKeyHeader = Annotated[
    str | None,
    Header(
        alias="X-Idempotency-Key",
        description=("Optional idempotency key to make retries safe for the same logical request."),
    ),
]


def create_ingestion_job_id() -> str:
    return f"job_{uuid4().hex}"


def get_request_lineage() -> tuple[str, str, str]:
    return (
        correlation_id_var.get(),
        request_id_var.get(),
        trace_id_var.get(),
    )
