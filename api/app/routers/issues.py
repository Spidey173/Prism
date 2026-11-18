from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.issues import DocumentHealth, IssueFeedbackRequest, IssueFeedbackResponse, IssueView
from app.services.issue_service import read_health, read_issues, record_feedback

router = APIRouter(tags=["issues"])


@router.get("/documents/{document_id}/issues", response_model=list[IssueView])
def document_issues(
    document_id: UUID,
    type: str | None = None,
    detector: str | None = None,
    severity: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
) -> list[IssueView]:
    return read_issues(db, document_id, type, detector, severity, status)


@router.get("/documents/{document_id}/health", response_model=DocumentHealth)
def document_health(document_id: UUID, db: Session = Depends(get_db)) -> DocumentHealth:
    return read_health(db, document_id)


@router.post("/issues/{issue_id}/feedback", response_model=IssueFeedbackResponse)
def issue_feedback(
    issue_id: UUID,
    request: IssueFeedbackRequest,
    db: Session = Depends(get_db),
) -> IssueFeedbackResponse:
    return record_feedback(db, issue_id, request)
