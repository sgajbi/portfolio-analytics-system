from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.DTOs.ingestion_job_dto import (
    IngestionHealthSummaryResponse,
    IngestionJobFailureResponse,
    IngestionJobResponse,
    IngestionJobStatus,
)
from portfolio_common.database_models import (
    IngestionJob as DBIngestionJob,
)
from portfolio_common.database_models import (
    IngestionJobFailure as DBIngestionJobFailure,
)
from portfolio_common.db import get_async_db_session
from sqlalchemy import and_, desc, func, select


@dataclass(slots=True)
class IngestionJobReplayContext:
    job_id: str
    endpoint: str
    entity_type: str
    accepted_count: int
    idempotency_key: str | None
    request_payload: dict[str, Any] | None


@dataclass(slots=True)
class IngestionJobCreateResult:
    job: IngestionJobResponse
    created: bool


def _to_response(job: DBIngestionJob) -> IngestionJobResponse:
    return IngestionJobResponse(
        job_id=job.job_id,
        endpoint=job.endpoint,
        entity_type=job.entity_type,
        status=job.status,  # type: ignore[arg-type]
        accepted_count=job.accepted_count,
        idempotency_key=job.idempotency_key,
        correlation_id=job.correlation_id,
        request_id=job.request_id,
        trace_id=job.trace_id,
        submitted_at=job.submitted_at,
        completed_at=job.completed_at,
        failure_reason=job.failure_reason,
        retry_count=job.retry_count,
        last_retried_at=job.last_retried_at,
    )


def _to_failure_response(failure: DBIngestionJobFailure) -> IngestionJobFailureResponse:
    return IngestionJobFailureResponse(
        failure_id=failure.failure_id,
        job_id=failure.job_id,
        failure_phase=failure.failure_phase,
        failure_reason=failure.failure_reason,
        failed_at=failure.failed_at,
    )


class IngestionJobService:
    """
    Persists ingestion request lifecycle for API-first operational visibility.
    """

    async def create_or_get_job(
        self,
        *,
        job_id: str,
        endpoint: str,
        entity_type: str,
        accepted_count: int,
        idempotency_key: str | None,
        correlation_id: str,
        request_id: str,
        trace_id: str,
        request_payload: dict[str, Any] | None,
    ) -> IngestionJobCreateResult:
        async for db in get_async_db_session():
            async with db.begin():
                if idempotency_key:
                    existing = await db.scalar(
                        select(DBIngestionJob)
                        .where(
                            and_(
                                DBIngestionJob.endpoint == endpoint,
                                DBIngestionJob.idempotency_key == idempotency_key,
                            )
                        )
                        .order_by(desc(DBIngestionJob.submitted_at))
                        .limit(1)
                    )
                    if existing is not None:
                        return IngestionJobCreateResult(job=_to_response(existing), created=False)

                row = DBIngestionJob(
                    job_id=job_id,
                    endpoint=endpoint,
                    entity_type=entity_type,
                    status="accepted",
                    accepted_count=accepted_count,
                    idempotency_key=idempotency_key,
                    correlation_id=correlation_id,
                    request_id=request_id,
                    trace_id=trace_id,
                    request_payload=request_payload,
                )
                db.add(row)
                await db.flush()
                return IngestionJobCreateResult(job=_to_response(row), created=True)

        msg = "Unable to create ingestion job due to unavailable database session."
        raise RuntimeError(msg)

    async def mark_queued(self, job_id: str) -> None:
        async for db in get_async_db_session():
            async with db.begin():
                row = await db.scalar(
                    select(DBIngestionJob).where(DBIngestionJob.job_id == job_id).limit(1)
                )
                if row is None:
                    return
                row.status = "queued"
                row.completed_at = datetime.now(UTC)
                row.failure_reason = None

    async def mark_failed(
        self, job_id: str, failure_reason: str, failure_phase: str = "publish"
    ) -> None:
        async for db in get_async_db_session():
            async with db.begin():
                row = await db.scalar(
                    select(DBIngestionJob).where(DBIngestionJob.job_id == job_id).limit(1)
                )
                if row is None:
                    return
                row.status = "failed"
                row.completed_at = datetime.now(UTC)
                row.failure_reason = failure_reason
                db.add(
                    DBIngestionJobFailure(
                        failure_id=f"fail_{uuid4().hex}",
                        job_id=job_id,
                        failure_phase=failure_phase,
                        failure_reason=failure_reason,
                    )
                )

    async def mark_retried(self, job_id: str) -> None:
        async for db in get_async_db_session():
            async with db.begin():
                row = await db.scalar(
                    select(DBIngestionJob).where(DBIngestionJob.job_id == job_id).limit(1)
                )
                if row is None:
                    return
                row.retry_count = int(row.retry_count or 0) + 1
                row.last_retried_at = datetime.now(UTC)

    async def get_job(self, job_id: str) -> IngestionJobResponse | None:
        async for db in get_async_db_session():
            row = await db.scalar(
                select(DBIngestionJob).where(DBIngestionJob.job_id == job_id).limit(1)
            )
            return _to_response(row) if row else None
        return None

    async def get_job_replay_context(self, job_id: str) -> IngestionJobReplayContext | None:
        async for db in get_async_db_session():
            row = await db.scalar(
                select(DBIngestionJob).where(DBIngestionJob.job_id == job_id).limit(1)
            )
            if row is None:
                return None
            payload = row.request_payload if isinstance(row.request_payload, dict) else None
            return IngestionJobReplayContext(
                job_id=row.job_id,
                endpoint=row.endpoint,
                entity_type=row.entity_type,
                accepted_count=row.accepted_count,
                idempotency_key=row.idempotency_key,
                request_payload=payload,
            )
        return None

    async def list_jobs(
        self,
        *,
        status: IngestionJobStatus | None = None,
        entity_type: str | None = None,
        submitted_from: datetime | None = None,
        submitted_to: datetime | None = None,
        cursor: str | None = None,
        limit: int = 100,
    ) -> tuple[list[IngestionJobResponse], str | None]:
        async for db in get_async_db_session():
            stmt = select(DBIngestionJob)
            if status is not None:
                stmt = stmt.where(DBIngestionJob.status == status)
            if entity_type is not None:
                stmt = stmt.where(DBIngestionJob.entity_type == entity_type)
            if submitted_from is not None:
                stmt = stmt.where(DBIngestionJob.submitted_at >= submitted_from)
            if submitted_to is not None:
                stmt = stmt.where(DBIngestionJob.submitted_at <= submitted_to)
            if cursor is not None:
                cursor_row = await db.scalar(
                    select(DBIngestionJob).where(DBIngestionJob.job_id == cursor).limit(1)
                )
                if cursor_row is not None:
                    stmt = stmt.where(DBIngestionJob.id < cursor_row.id)
            stmt = stmt.order_by(desc(DBIngestionJob.id)).limit(limit + 1)
            rows = list((await db.scalars(stmt)).all())
            has_more = len(rows) > limit
            page_rows = rows[:limit]
            next_cursor = page_rows[-1].job_id if has_more and page_rows else None
            return ([_to_response(row) for row in page_rows], next_cursor)
        return ([], None)

    async def list_failures(
        self, job_id: str, limit: int = 100
    ) -> list[IngestionJobFailureResponse]:
        async for db in get_async_db_session():
            rows = (
                await db.scalars(
                    select(DBIngestionJobFailure)
                    .where(DBIngestionJobFailure.job_id == job_id)
                    .order_by(desc(DBIngestionJobFailure.failed_at))
                    .limit(limit)
                )
            ).all()
            return [_to_failure_response(row) for row in rows]
        return []

    async def get_health_summary(self) -> IngestionHealthSummaryResponse:
        async for db in get_async_db_session():
            total_jobs = int((await db.scalar(select(func.count(DBIngestionJob.id)))) or 0)
            accepted_jobs = int(
                (
                    await db.scalar(
                        select(func.count(DBIngestionJob.id)).where(
                            DBIngestionJob.status == "accepted"
                        )
                    )
                )
                or 0
            )
            queued_jobs = int(
                (
                    await db.scalar(
                        select(func.count(DBIngestionJob.id)).where(
                            DBIngestionJob.status == "queued"
                        )
                    )
                )
                or 0
            )
            failed_jobs = int(
                (
                    await db.scalar(
                        select(func.count(DBIngestionJob.id)).where(
                            DBIngestionJob.status == "failed"
                        )
                    )
                )
                or 0
            )
            return IngestionHealthSummaryResponse(
                total_jobs=total_jobs,
                accepted_jobs=accepted_jobs,
                queued_jobs=queued_jobs,
                failed_jobs=failed_jobs,
                backlog_jobs=accepted_jobs + queued_jobs,
            )
        return IngestionHealthSummaryResponse(
            total_jobs=0,
            accepted_jobs=0,
            queued_jobs=0,
            failed_jobs=0,
            backlog_jobs=0,
        )


_INGESTION_JOB_SERVICE = IngestionJobService()


def get_ingestion_job_service() -> IngestionJobService:
    return _INGESTION_JOB_SERVICE
