import logging

from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from app.DTOs.upload_dto import UploadCommitResponse, UploadEntityType, UploadPreviewResponse
from app.services.upload_ingestion_service import (
    UploadIngestionService,
    get_upload_ingestion_service,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/ingest/uploads/preview",
    response_model=UploadPreviewResponse,
    status_code=status.HTTP_200_OK,
    tags=["Bulk Uploads"],
    summary="Preview and validate bulk upload data",
    description=(
        "Validates CSV/XLSX rows against PAS ingestion contracts without publishing events. "
        "Returns row-level errors and normalized sample rows for UI correction workflows."
    ),
)
async def preview_upload(
    entity_type: UploadEntityType = Form(..., alias="entityType"),
    file: UploadFile = File(...),
    sample_size: int = Form(20, alias="sampleSize", ge=1, le=100),
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
    tags=["Bulk Uploads"],
    summary="Commit validated bulk upload data",
    description=(
        "Validates CSV/XLSX rows and publishes valid records to existing PAS ingestion topics. "
        "By default rejects partial uploads; set allowPartial=true to publish valid rows only."
    ),
)
async def commit_upload(
    entity_type: UploadEntityType = Form(..., alias="entityType"),
    file: UploadFile = File(...),
    allow_partial: bool = Form(False, alias="allowPartial"),
    upload_service: UploadIngestionService = Depends(get_upload_ingestion_service),
):
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
