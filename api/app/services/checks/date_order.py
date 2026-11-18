from collections import defaultdict
from datetime import date, datetime
import re

from app.services.checks.types import FactRecord, Finding

_START_WORDS = {"start", "begin", "commencement"}
_END_WORDS = {"end", "finish", "completion"}


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    clean = value.strip().replace(".", "")
    formats = (
        "%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d/%m/%Y",
        "%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y", "%Y",
    )
    for date_format in formats:
        try:
            return datetime.strptime(clean, date_format).date()
        except ValueError:
            pass
    match = re.search(r"\b(19|20)\d{2}\b", clean)
    return date(int(match.group(0)), 1, 1) if match else None


def detect_date_order(facts: list[FactRecord]) -> list[Finding]:
    by_subject: dict[str, list[FactRecord]] = defaultdict(list)
    for fact in facts:
        if (fact.unit_normalized or "").casefold() == "date":
            by_subject[fact.subject.casefold().strip()].append(fact)

    findings: list[Finding] = []
    for items in by_subject.values():
        starts = [fact for fact in items if any(word in fact.metric.casefold().split() for word in _START_WORDS)]
        ends = [fact for fact in items if any(word in fact.metric.casefold().split() for word in _END_WORDS)]
        for start_fact in starts:
            start_date = _parse_date(start_fact.raw_value)
            if start_date is None:
                continue
            for end_fact in ends:
                end_date = _parse_date(end_fact.raw_value)
                if end_date is None or end_date >= start_date:
                    continue
                findings.append(
                    Finding(
                        issue_type="date_order",
                        detector="date_order",
                        severity="high",
                        title="End date comes before start date",
                        explanation=f"The stated end date {end_fact.raw_value} is earlier than the start date {start_fact.raw_value}.",
                        confidence=0.99,
                        evidence=(start_fact, end_fact),
                    )
                )
    return findings
