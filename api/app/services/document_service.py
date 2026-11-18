from __future__ import annotations

import hashlib
import structlog
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import delete, func, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.audit import AuditRun, Document, Page, TextChunk
from app.repositories.documents import chunks_for_page, find_by_hash, get_document, get_page, latest_run
from app.schemas.documents import AuditStatus, ChunkAnnotation, DocumentCreated, PageAnnotations
from app.services.pdf_parser import ScannedPdfError, parse_pdf
from app.services.llm import LLMClient

logger = structlog.get_logger(__name__)


def _response_for_existing(db: Session, document: Document) -> DocumentCreated:
    run = latest_run(db, document.id)
    if run is None:
        raise HTTPException(status_code=500, detail="Document has no audit run.")
    return DocumentCreated(
        id=document.id,
        audit_run_id=run.id,
        deduplicated=True,
        status=run.status,
        error=run.error,
    )


def create_upload(db: Session, upload: UploadFile, data: bytes) -> DocumentCreated:
    settings = get_settings()
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"PDF exceeds the {settings.max_upload_bytes}-byte upload limit.",
        )
    if not data.startswith(b"%PDF-"):
        raise HTTPException(status_code=415, detail="Upload must be a PDF beginning with %PDF-.")

    content_hash = hashlib.sha256(data).hexdigest()
    existing = find_by_hash(db, content_hash)
    if existing is not None:
        return _response_for_existing(db, existing)

    upload_dir = Path(settings.upload_dir).expanduser().resolve()
    upload_dir.mkdir(parents=True, exist_ok=True)
    document_id = uuid.uuid4()
    stored_path = upload_dir / f"{document_id}.pdf"
    temporary_path = stored_path.with_suffix(".pdf.tmp")
    temporary_path.write_bytes(data)
    temporary_path.replace(stored_path)

    document = Document(
        id=document_id,
        filename=(upload.filename or "document.pdf")[:512],
        content_hash=content_hash,
        storage_path=str(stored_path),
    )
    run = AuditRun(document_id=document_id, status="queued", stage="parsing", progress=0)
    db.add_all([document, run])
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        stored_path.unlink(missing_ok=True)
        duplicate = find_by_hash(db, content_hash)
        if duplicate is not None:
            return _response_for_existing(db, duplicate)
        raise
    db.refresh(run)
    return DocumentCreated(
        id=document.id,
        audit_run_id=run.id,
        deduplicated=False,
        status=run.status,
        error=None,
    )


def process_document(document_id: uuid.UUID, llm_client: LLMClient | None = None) -> None:
    started = time.perf_counter()
    db = SessionLocal()
    run: AuditRun | None = None
    try:
        document = get_document(db, document_id)
        run = latest_run(db, document_id)
        if document is None or run is None:
            return
        if run.status in {"done", "failed"}:
            return

        run.status = "running"
        run.stage = "parsing"
        run.progress = 5
        run.started_at = run.started_at or datetime.now(timezone.utc)
        run.stage_timings = {}
        db.commit()

        pdf_bytes = Path(document.storage_path).read_bytes()
        parsed = parse_pdf(pdf_bytes, max_pages=get_settings().max_pdf_pages)
        db.execute(delete(TextChunk).where(TextChunk.document_id == document_id))
        db.execute(delete(Page).where(Page.document_id == document_id))
        page_models = [
            Page(
                document_id=document_id,
                page_number=page.page_number,
                width=page.width,
                height=page.height,
                text=page.text,
            )
            for page in parsed.pages
        ]
        db.add_all(page_models)
        db.flush()
        page_ids = {page.page_number: page.id for page in page_models}
        run.stage = "embedding"
        run.progress = 35
        db.commit()
        from fastembed import TextEmbedding

        model = TextEmbedding(model_name=get_settings().fastembed_model)
        embeddings = list(model.embed([segment.text for segment in parsed.segments]))
        chunk_counts: dict[int, int] = {}
        chunks: list[TextChunk] = []
        for segment, embedding in zip(parsed.segments, embeddings, strict=True):
            page_index = chunk_counts.get(segment.page_number, 0)
            chunk_counts[segment.page_number] = page_index + 1
            chunks.append(
                TextChunk(
                    document_id=document_id,
                    page_id=page_ids[segment.page_number],
                    chunk_index=page_index,
                    sentence_id=segment.sentence_id,
                    segment_index=segment.segment_index,
                    chunk_type=segment.chunk_type,
                    text=segment.text,
                    bboxes=segment.bboxes,
                    table_cells=segment.table_cells,
                    table_bbox=segment.table_bbox,
                    header_row=segment.header_row,
                    embedding=[float(value) for value in embedding],
                )
            )
        db.add_all(chunks)
        db.commit()

        stage_timings: dict[str, float] = {"ingestion_seconds": round(time.perf_counter() - started, 3)}
        stage_started = time.perf_counter()
        run.stage = "extracting"
        run.progress = 55
        db.commit()
        from app.services.fact_extraction import extract_facts

        settings = get_settings()
        shared_client = None
        if llm_client is not None:
            from app.services.fact_extraction import budgeted_client

            shared_client = budgeted_client(db, run, settings, llm_client)
        extract_facts(db, run, document_id, settings, llm_client=shared_client)
        stage_timings["fact_extraction_seconds"] = round(time.perf_counter() - stage_started, 3)

        stage_started = time.perf_counter()
        run.stage = "checking"
        run.progress = 82
        db.commit()
        from app.services.checks.runner import run_deterministic_checks

        run_deterministic_checks(db, run, document_id)
        stage_timings["deterministic_checks_seconds"] = round(time.perf_counter() - stage_started, 3)

        stage_started = time.perf_counter()
        run.stage = "semantic"
        run.progress = 92
        db.commit()
        from app.services.semantic_audit import run_semantic_audit

        run_semantic_audit(db, run, document_id, settings, llm_client=shared_client)
        stage_timings["semantic_check_seconds"] = round(time.perf_counter() - stage_started, 3)

        run.stage = "done"
        run.progress = 100
        run.status = "done"
        run.finished_at = datetime.now(timezone.utc)
        run.stage_timings = {**run.stage_timings, **stage_timings}
        db.commit()
        logger.info("document_audit_completed", document_id=str(document_id), chunks=len(chunks), timings=stage_timings)
    except ScannedPdfError as exc:
        _mark_failed(db, document_id, str(exc))
    except Exception as exc:
        logger.exception("document_ingestion_failed", document_id=str(document_id))
        _mark_failed(db, document_id, str(exc))
    finally:
        db.close()


def _mark_failed(db: Session, document_id: uuid.UUID, reason: str) -> None:
    db.rollback()
    run = latest_run(db, document_id)
    if run is None:
        return
    run.status = "failed"
    run.stage = "failed"
    run.error = reason[:4000]
    run.finished_at = datetime.now(timezone.utc)
    db.commit()


def mark_interrupted_runs_failed() -> None:
    with SessionLocal() as db:
        db.execute(
            update(AuditRun)
            .where(AuditRun.status.in_(["running", "queued"]))
            .values(
                status="failed",
                stage="failed",
                error="Processing was interrupted by an API restart before completion.",
                finished_at=func.now(),
            )
        )
        db.commit()


def read_status(db: Session, document_id: uuid.UUID) -> AuditStatus:
    document = get_document(db, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    run = latest_run(db, document_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Audit run not found.")
    return AuditStatus(
        document_id=document_id,
        audit_run_id=run.id,
        status=run.status,
        stage=run.stage,
        progress=run.progress,
        error=run.error,
    )


def read_page_annotations(db: Session, document_id: uuid.UUID, page_number: int) -> PageAnnotations:
    page = get_page(db, document_id, page_number)
    if page is None:
        raise HTTPException(status_code=404, detail="Page not found or document is not parsed yet.")
    chunks = chunks_for_page(db, page.id)
    return PageAnnotations(
        document_id=document_id,
        page_number=page.page_number,
        width=page.width,
        height=page.height,
        chunks=[
            ChunkAnnotation(
                id=chunk.id,
                sentence_id=chunk.sentence_id,
                segment_index=chunk.segment_index,
                page_number=page.page_number,
                text=chunk.text,
                bboxes=chunk.bboxes,
                chunk_type=chunk.chunk_type,
                table_cells=chunk.table_cells,
                table_bbox=chunk.table_bbox,
                header_row=chunk.header_row,
            )
            for chunk in chunks
        ],
    )


def document_file_path(db: Session, document_id: uuid.UUID) -> tuple[Path, str]:
    document = get_document(db, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    path = Path(document.storage_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Stored PDF file is missing.")
    return path, document.filename
