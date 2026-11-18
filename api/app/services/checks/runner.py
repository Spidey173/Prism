from __future__ import annotations

import hashlib
import json
from uuid import UUID

import structlog
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.audit import AuditRun, Fact, Issue, IssueEvidence, Page, TextChunk
from app.services.checks import (
    detect_date_order,
    detect_percent_mismatch,
    detect_same_metric_conflict,
    detect_sum_mismatch,
)
from app.services.checks.types import FactRecord

logger = structlog.get_logger(__name__)


def run_deterministic_checks(db: Session, run: AuditRun, document_id: UUID) -> int:
    db.execute(delete(IssueEvidence).where(IssueEvidence.issue_id.in_(select(Issue.id).where(Issue.audit_run_id == run.id))))
    db.execute(delete(Issue).where(Issue.audit_run_id == run.id))
    rows = db.execute(
        select(Fact, Page.id, TextChunk.bboxes, TextChunk.chunk_type, TextChunk.table_cells)
        .join(Page, (Fact.page_number == Page.page_number) & (Page.document_id == document_id))
        .join(TextChunk, Fact.chunk_id == TextChunk.id)
        .where(Fact.document_id == document_id, Fact.audit_run_id == run.id)
    ).all()
    records = [
        FactRecord(
            id=fact.id,
            chunk_id=fact.chunk_id,
            page_id=page_id,
            page_number=fact.page_number,
            subject=fact.subject,
            metric=fact.metric,
            value_num=fact.value_num,
            value_low=fact.value_low,
            value_high=fact.value_high,
            unit_normalized=fact.unit_normalized,
            period=fact.period,
            raw_value=fact.raw_value,
            quote=fact.quote,
            bboxes=(
                [cell["bbox"] for cell in table_cells if cell.get("row") == fact.table_row and cell.get("col") == fact.table_col and isinstance(cell.get("bbox"), list)]
                or bboxes
            ),
            scale=fact.scale.value if hasattr(fact.scale, "value") else str(fact.scale),
            chunk_type=chunk_type,
            table_row=fact.table_row,
            table_col=fact.table_col,
        )
        for fact, page_id, bboxes, chunk_type, table_cells in rows
    ]
    findings = [
        *detect_same_metric_conflict(records),
        *detect_sum_mismatch(records),
        *detect_percent_mismatch(records),
        *detect_date_order(records),
    ]
    for finding in findings:
        evidence_keys = sorted({str(item.id) for item in finding.evidence})
        fingerprint = hashlib.sha256(
            json.dumps([finding.issue_type, evidence_keys], separators=(",", ":")).encode()
        ).hexdigest()
        issue = Issue(
            document_id=document_id,
            audit_run_id=run.id,
            type=finding.issue_type,
            detector=finding.detector,
            fingerprint=fingerprint,
            severity=finding.severity,
            title=finding.title,
            explanation=finding.explanation,
            confidence=finding.confidence,
        )
        db.add(issue)
        db.flush()
        evidence_order = 0
        for fact_record in finding.evidence:
            source_chunk = db.get(TextChunk, fact_record.chunk_id)
            locations = [(fact_record.page_id, fact_record.page_number, fact_record.bboxes, fact_record.chunk_id)]
            if source_chunk is not None and source_chunk.chunk_type == "sentence":
                sibling_rows = db.execute(
                    select(TextChunk, Page.id, Page.page_number)
                    .join(Page, TextChunk.page_id == Page.id)
                    .where(TextChunk.sentence_id == source_chunk.sentence_id)
                    .order_by(Page.page_number, TextChunk.segment_index)
                ).all()
                if sibling_rows:
                    locations = [(page_id, page_number, sibling.bboxes, sibling.id) for sibling, page_id, page_number in sibling_rows]
            for page_id, page_number, bboxes, chunk_id in locations:
                db.add(
                    IssueEvidence(
                        issue_id=issue.id,
                        page_id=page_id,
                        chunk_id=chunk_id,
                        page_number=page_number,
                        bboxes=bboxes,
                        quote=fact_record.quote,
                        evidence_order=evidence_order,
                    )
                )
                evidence_order += 1
    db.commit()
    logger.info("deterministic_checks_completed", document_id=str(document_id), issues=len(findings))
    return len(findings)
