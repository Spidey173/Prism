from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class IssueEvidenceView(BaseModel):
    page_number: int
    bboxes: list[list[float]]
    quote: str


class IssueView(BaseModel):
    id: UUID
    type: str
    detector: str
    severity: str
    status: str
    title: str
    explanation: str
    confidence: float
    needs_review: bool
    conflicting_span_a: str | None = None
    conflicting_span_b: str | None = None
    evidence: list[IssueEvidenceView]


class IssueFeedbackRequest(BaseModel):
    feedback: Literal["confirm", "false_positive"]
    note: str | None = None


class IssueFeedbackResponse(BaseModel):
    id: UUID
    status: str


class DocumentHealth(BaseModel):
    document_id: UUID
    score: int
    high: int
    med: int
    low: int
