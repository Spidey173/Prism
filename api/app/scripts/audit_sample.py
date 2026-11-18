from __future__ import annotations

import argparse
import json
from io import BytesIO
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import select, func

from app.db.session import SessionLocal
from app.models.audit import AuditRun, Fact, Issue
from app.repositories.documents import latest_run
from app.scripts.sample_fake import sample_fake_response
from app.services.document_service import create_upload, process_document
from app.services.llm import FakeLLMClient


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the full document audit against the planted-error sample.")
    parser.add_argument("--fake-llm", action="store_true", help="Use a deterministic FakeLLMClient; no API key is needed.")
    args = parser.parse_args()
    sample_path = Path(__file__).resolve().parents[3] / "samples" / "phase2_planted_errors.pdf"
    if not sample_path.is_file():
        parser.error(f"Sample PDF is missing: {sample_path}")
    data = sample_path.read_bytes()

    with SessionLocal() as db:
        uploaded = UploadFile(filename=sample_path.name, file=BytesIO(data))
        result = create_upload(db, uploaded, data)
        if result.deduplicated:
            run = AuditRun(document_id=result.id, status="queued", stage="parsing", progress=0)
            db.add(run)
            db.commit()
        process_document(
            result.id,
            llm_client=FakeLLMClient(handler=sample_fake_response) if args.fake_llm else None,
        )
        db.expire_all()
        run = latest_run(db, result.id)
        if run is None:
            print("Audit did not create an audit run.")
            return 1
        fact_count = db.scalar(select(func.count(Fact.id)).where(Fact.audit_run_id == run.id)) or 0
        issues = list(db.scalars(select(Issue).where(Issue.audit_run_id == run.id).order_by(Issue.severity, Issue.type)))
        report = {
            "document_id": str(result.id),
            "audit_run_id": str(run.id),
            "status": run.status,
            "error": run.error,
            "stage_timings": run.stage_timings,
            "fact_count": fact_count,
            "issue_count": len(issues),
            "tokens_used": run.tokens_used,
            "estimated_cost_usd": str(run.estimated_cost),
            "issues": [
                {
                    "type": issue.type,
                    "detector": issue.detector,
                    "severity": issue.severity,
                    "needs_review": issue.needs_review,
                    "title": issue.title,
                }
                for issue in issues
            ],
            "fake_llm": args.fake_llm,
        }
        print(json.dumps(report, indent=2))
        return 0 if run.status == "done" else 1


if __name__ == "__main__":
    raise SystemExit(main())
