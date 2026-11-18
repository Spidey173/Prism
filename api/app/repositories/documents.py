from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.audit import AuditRun, Document, Page, TextChunk


def find_by_hash(db: Session, content_hash: str) -> Document | None:
    return db.scalar(select(Document).where(Document.content_hash == content_hash))


def get_document(db: Session, document_id: UUID) -> Document | None:
    return db.get(Document, document_id)


def latest_run(db: Session, document_id: UUID) -> AuditRun | None:
    return db.scalar(
        select(AuditRun)
        .where(AuditRun.document_id == document_id)
        .order_by(desc(AuditRun.created_at))
        .limit(1)
    )


def get_page(db: Session, document_id: UUID, page_number: int) -> Page | None:
    return db.scalar(
        select(Page).where(Page.document_id == document_id, Page.page_number == page_number)
    )


def chunks_for_page(db: Session, page_id: UUID) -> list[TextChunk]:
    return list(db.scalars(select(TextChunk).where(TextChunk.page_id == page_id).order_by(TextChunk.chunk_index)))
