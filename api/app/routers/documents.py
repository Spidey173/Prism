from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.schemas.documents import AuditStatus, DocumentCreated, PageAnnotations
from app.services.document_service import (
    create_upload,
    document_file_path,
    process_document,
    read_page_annotations,
    read_status,
)

router = APIRouter(tags=["documents"])


@router.post("/documents", response_model=DocumentCreated)
def upload_document(
    background_tasks: BackgroundTasks,
    response: Response,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> DocumentCreated:
    data = file.file.read(get_settings().max_upload_bytes + 1)
    result = create_upload(db, file, data)
    if result.deduplicated:
        response.status_code = 200
    else:
        response.status_code = 202
        background_tasks.add_task(process_document, result.id)
    return result


@router.get("/documents/{document_id}/status", response_model=AuditStatus)
def document_status(document_id: UUID, db: Session = Depends(get_db)) -> AuditStatus:
    return read_status(db, document_id)


@router.get("/documents/{document_id}/pages/{page_number}/annotations", response_model=PageAnnotations)
def page_annotations(
    document_id: UUID, page_number: int, db: Session = Depends(get_db)
) -> PageAnnotations:
    if page_number < 1:
        raise HTTPException(status_code=422, detail="Page numbers start at 1.")
    return read_page_annotations(db, document_id, page_number)


@router.get("/documents/{document_id}/file")
def download_document(document_id: UUID, db: Session = Depends(get_db)) -> FileResponse:
    path, filename = document_file_path(db, document_id)
    return FileResponse(path, media_type="application/pdf", filename=filename)
