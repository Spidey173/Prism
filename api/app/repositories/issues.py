from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit import Issue, IssueEvidence


def get_issue(db: Session, issue_id: UUID) -> Issue | None:
    return db.get(Issue, issue_id)


def list_issues(
    db: Session,
    document_id: UUID,
    audit_run_id: UUID | None = None,
    issue_type: str | None = None,
    detector: str | None = None,
    severity: str | None = None,
    issue_status: str | None = None,
) -> list[Issue]:
    statement = select(Issue).where(Issue.document_id == document_id)
    if audit_run_id is not None:
        statement = statement.where(Issue.audit_run_id == audit_run_id)
    if issue_type:
        statement = statement.where(Issue.type == issue_type)
    if detector:
        statement = statement.where(Issue.detector == detector)
    if severity:
        statement = statement.where(Issue.severity == severity)
    if issue_status:
        statement = statement.where(Issue.status == issue_status)
    return list(db.scalars(statement.order_by(Issue.created_at.desc())))


def evidence_for_issue(db: Session, issue_id: UUID) -> list[IssueEvidence]:
    return list(db.scalars(select(IssueEvidence).where(IssueEvidence.issue_id == issue_id).order_by(IssueEvidence.evidence_order)))
