from collections import Counter
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.audit import IssueFeedback
from app.repositories.documents import get_document, latest_run
from app.repositories.issues import evidence_for_issue, get_issue, list_issues
from app.schemas.issues import DocumentHealth, IssueEvidenceView, IssueFeedbackRequest, IssueFeedbackResponse, IssueView

_SEVERITY_WEIGHT = {"high": 15, "med": 7, "low": 3}


def read_issues(
    db: Session,
    document_id: UUID,
    issue_type: str | None,
    detector: str | None,
    severity: str | None,
    issue_status: str | None,
) -> list[IssueView]:
    if get_document(db, document_id) is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    severity_order = {"high": 0, "med": 1, "low": 2}
    run = latest_run(db, document_id)
    if run is None:
        return []
    issues = list_issues(db, document_id, run.id, issue_type, detector, severity, issue_status)
    issues.sort(key=lambda issue: (severity_order.get(issue.severity, 3), issue.created_at))
    return [
        IssueView(
            id=issue.id,
            type=issue.type,
            detector=issue.detector,
            severity=issue.severity,
            status=issue.status,
            title=issue.title,
            explanation=issue.explanation,
            confidence=issue.confidence,
            needs_review=issue.needs_review,
            conflicting_span_a=issue.conflicting_span_a,
            conflicting_span_b=issue.conflicting_span_b,
            evidence=[
                IssueEvidenceView(page_number=item.page_number, bboxes=item.bboxes, quote=item.quote)
                for item in evidence_for_issue(db, issue.id)
            ],
        )
        for issue in issues
    ]


def record_feedback(db: Session, issue_id: UUID, request: IssueFeedbackRequest) -> IssueFeedbackResponse:
    issue = get_issue(db, issue_id)
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found.")
    new_status = "confirmed" if request.feedback == "confirm" else "false_positive"
    db.add(IssueFeedback(issue_id=issue.id, feedback=request.feedback, note=request.note))
    issue.status = new_status
    db.commit()
    return IssueFeedbackResponse(id=issue.id, status=new_status)


def read_health(db: Session, document_id: UUID) -> DocumentHealth:
    if get_document(db, document_id) is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    run = latest_run(db, document_id)
    open_issues = list_issues(db, document_id, run.id if run else None, issue_status="open")
    counts = Counter(issue.severity for issue in open_issues)
    score = max(0, 100 - sum(counts[level] * weight for level, weight in _SEVERITY_WEIGHT.items()))
    return DocumentHealth(document_id=document_id, score=score, high=counts["high"], med=counts["med"], low=counts["low"])
