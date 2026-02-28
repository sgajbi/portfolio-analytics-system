import logging

from app.adapter_mode import require_upload_adapter_enabled
from app.DTOs.upload_dto import UploadCommitResponse, UploadEntityType, UploadPreviewResponse
from app.services.ingestion_job_service import IngestionJobService, get_ingestion_job_service
from app.services.upload_ingestion_service import (
    UploadIngestionService,
    get_upload_ingestion_service,
)
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/ingest/uploads/preview",
    response_model=UploadPreviewResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "description": "Invalid upload file format or content.",
        },
        status.HTTP_410_GONE: {
            "description": "Bulk upload adapter mode disabled for this environment.",
        },
    },
    tags=["Bulk Uploads"],
    summary="Preview and validate bulk upload data",
    description=(
        "Validates CSV/XLSX rows against lotus-core ingestion contracts without publishing events. "
        "Returns row-level errors and normalized sample rows for UI correction workflows."
    ),
)
async def preview_upload(
    entity_type: UploadEntityType = Form(...),
    file: UploadFile = File(...),
    sample_size: int = Form(20, ge=1, le=100),
    _: None = Depends(require_upload_adapter_enabled),
    upload_service: UploadIngestionService = Depends(get_upload_ingestion_service),
):
    content = await file.read()
    response = upload_service.preview_upload(
        entity_type=entity_type,
        filename=file.filename or "upload.csv",
        content=content,
        sample_size=sample_size,
    )
    logger.info(
        "Upload preview completed.",
        extra={
            "entity_type": entity_type,
            "upload_filename": file.filename,
            "total_rows": response.total_rows,
            "valid_rows": response.valid_rows,
            "invalid_rows": response.invalid_rows,
        },
    )
    return response


@router.post(
    "/ingest/uploads/commit",
    response_model=UploadCommitResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "description": "Invalid upload file format or content.",
        },
        status.HTTP_410_GONE: {
            "description": "Bulk upload adapter mode disabled for this environment.",
        },
    },
    tags=["Bulk Uploads"],
    summary="Commit validated bulk upload data",
    description=(
        "Validates CSV/XLSX rows and publishes valid records to "
        "existing lotus-core ingestion topics. "
        "By default rejects partial uploads; set allowPartial=true to publish valid rows only."
    ),
)
async def commit_upload(
    entity_type: UploadEntityType = Form(...),
    file: UploadFile = File(...),
    allow_partial: bool = Form(False),
    _: None = Depends(require_upload_adapter_enabled),
    upload_service: UploadIngestionService = Depends(get_upload_ingestion_service),
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
):
    try:
        await ingestion_job_service.assert_ingestion_writable()
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "INGESTION_MODE_BLOCKS_WRITES", "message": str(exc)},
        ) from exc
    content = await file.read()
    response = await upload_service.commit_upload(
        entity_type=entity_type,
        filename=file.filename or "upload.csv",
        content=content,
        allow_partial=allow_partial,
    )
    logger.info(
        "Upload commit completed.",
        extra={
            "entity_type": entity_type,
            "upload_filename": file.filename,
            "published_rows": response.published_rows,
            "skipped_rows": response.skipped_rows,
        },
    )
    return response

