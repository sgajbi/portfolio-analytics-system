from uuid import uuid4

from fastapi import Request
from portfolio_common.logging_utils import correlation_id_var, request_id_var, trace_id_var


def resolve_idempotency_key(request: Request) -> str | None:
    return request.headers.get("X-Idempotency-Key")

def create_ingestion_job_id() -> str:
    return f"job_{uuid4().hex}"


def get_request_lineage() -> tuple[str, str, str]:
    return (
        correlation_id_var.get(),
        request_id_var.get(),
        trace_id_var.get(),
    )
