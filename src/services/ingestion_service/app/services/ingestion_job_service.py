from __future__ import annotations

from datetime import UTC, datetime

from app.DTOs.ingestion_job_dto import IngestionJobResponse, IngestionJobStatus
from portfolio_common.database_models import IngestionJob as DBIngestionJob
from portfolio_common.db import get_async_db_session
from sqlalchemy import desc, select


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
    )


class IngestionJobService:
    """
    Persists ingestion request lifecycle for API-first operational visibility.
    """

    async def create_job(
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
    ) -> None:
        async for db in get_async_db_session():
            async with db.begin():
                db.add(
                    DBIngestionJob(
                        job_id=job_id,
                        endpoint=endpoint,
                        entity_type=entity_type,
                        status="accepted",
                        accepted_count=accepted_count,
                        idempotency_key=idempotency_key,
                        correlation_id=correlation_id,
                        request_id=request_id,
                        trace_id=trace_id,
                    )
                )

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

    async def mark_failed(self, job_id: str, failure_reason: str) -> None:
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

    async def get_job(self, job_id: str) -> IngestionJobResponse | None:
        async for db in get_async_db_session():
            row = await db.scalar(
                select(DBIngestionJob).where(DBIngestionJob.job_id == job_id).limit(1)
            )
            return _to_response(row) if row else None
        return None

    async def list_jobs(
        self,
        *,
        status: IngestionJobStatus | None = None,
        entity_type: str | None = None,
        limit: int = 100,
    ) -> list[IngestionJobResponse]:
        async for db in get_async_db_session():
            stmt = select(DBIngestionJob)
            if status is not None:
                stmt = stmt.where(DBIngestionJob.status == status)
            if entity_type is not None:
                stmt = stmt.where(DBIngestionJob.entity_type == entity_type)
            stmt = stmt.order_by(desc(DBIngestionJob.submitted_at)).limit(limit)
            rows = (await db.scalars(stmt)).all()
            return [_to_response(row) for row in rows]
        return []


_INGESTION_JOB_SERVICE = IngestionJobService()


def get_ingestion_job_service() -> IngestionJobService:
    return _INGESTION_JOB_SERVICE
