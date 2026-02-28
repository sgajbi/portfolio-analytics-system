import logging

from app.DTOs.ingestion_job_dto import IngestionJobListResponse, IngestionJobResponse
from app.services.ingestion_job_service import IngestionJobService, get_ingestion_job_service
from fastapi import APIRouter, Depends, HTTPException, Query, status

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/ingestion/jobs/{job_id}",
    response_model=IngestionJobResponse,
    status_code=status.HTTP_200_OK,
    tags=["Ingestion Operations"],
    summary="Get ingestion job status",
    description="Returns ingestion job lifecycle status and operational metadata by job_id.",
)
async def get_ingestion_job(
    job_id: str,
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
):
    job = ingestion_job_service.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "INGESTION_JOB_NOT_FOUND",
                "message": f"Ingestion job '{job_id}' was not found.",
            },
        )
    return job


@router.get(
    "/ingestion/jobs",
    response_model=IngestionJobListResponse,
    status_code=status.HTTP_200_OK,
    tags=["Ingestion Operations"],
    summary="List ingestion jobs",
    description=(
        "Returns recent ingestion jobs for operational monitoring. "
        "Supports filtering by status and entity_type."
    ),
)
async def list_ingestion_jobs(
    status_filter: str | None = Query(default=None, alias="status"),
    entity_type: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
):
    status_value = status_filter if status_filter in {"accepted", "queued", "failed"} else None
    jobs = ingestion_job_service.list_jobs(
        status=status_value, entity_type=entity_type, limit=limit
    )
    return IngestionJobListResponse(jobs=jobs, total=len(jobs))
