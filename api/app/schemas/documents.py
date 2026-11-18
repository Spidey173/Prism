from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DocumentCreated(BaseModel):
    id: UUID
    audit_run_id: UUID
    deduplicated: bool
    status: str
    error: str | None = None


class AuditStatus(BaseModel):
    document_id: UUID
    audit_run_id: UUID
    status: str
    stage: str
    progress: int
    error: str | None = None


class ChunkAnnotation(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sentence_id: UUID
    segment_index: int
    page_number: int
    text: str
    bboxes: list[list[float]]
    chunk_type: str = "sentence"
    table_cells: list[dict[str, object]] = Field(default_factory=list)
    table_bbox: list[float] | None = None
    header_row: int | None = None


class PageAnnotations(BaseModel):
    document_id: UUID
    page_number: int
    width: float
    height: float
    chunks: list[ChunkAnnotation]
