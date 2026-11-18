from collections import defaultdict
from decimal import Decimal
import re

from app.services.checks.types import FactRecord, Finding

_BASE_WORDS = {"prior", "previous", "baseline", "starting", "original", "base"}
_CURRENT_WORDS = {"current", "latest", "ending", "final", "current-year"}
_PERCENT_WORDS = {"growth", "change", "percent", "percentage", "rate", "increase", "decrease"}


def _stem(metric: str) -> str:
    words = re.findall(r"[a-z0-9]+", metric.casefold())
    return " ".join(word for word in words if word not in _BASE_WORDS | _CURRENT_WORDS | _PERCENT_WORDS)


def detect_percent_mismatch(facts: list[FactRecord]) -> list[Finding]:
    subjects: dict[str, list[FactRecord]] = defaultdict(list)
    for fact in facts:
        subjects[fact.subject.casefold().strip()].append(fact)

    findings: list[Finding] = []
    for items in subjects.values():
        percentages = [
            fact for fact in items
            if fact.comparable_value is not None and (fact.unit_normalized or "").casefold() in {"%", "percent", "percentage"}
        ]
        bases = [fact for fact in items if fact.comparable_value is not None and any(word in fact.metric.casefold().split() for word in _BASE_WORDS)]
        currents = [fact for fact in items if fact.comparable_value is not None and any(word in fact.metric.casefold().split() for word in _CURRENT_WORDS)]
        for percent in percentages:
            stem = _stem(percent.metric)
            for base in bases:
                for current in currents:
                    if percent.chunk_type == "table" and percent.table_row is not None:
                        if base.chunk_id != percent.chunk_id or base.table_row != percent.table_row:
                            continue
                        if current.chunk_id != percent.chunk_id or current.table_row != percent.table_row:
                            continue
                    base_value = base.comparable_value
                    current_value = current.comparable_value
                    percent_value = percent.comparable_value
                    if base_value in (None, Decimal(0)) or current_value is None or percent_value is None or _stem(base.metric) != _stem(current.metric):
                        continue
                    if stem and stem != _stem(base.metric):
                        continue
                    expected = (current_value - base_value) / abs(base_value) * Decimal(100)
                    if abs(expected - percent_value) <= max(Decimal("1"), abs(expected) * Decimal("0.05")):
                        continue
                    findings.append(
                        Finding(
                            issue_type="percent_mismatch",
                            detector="percent_mismatch",
                            severity="med",
                            title="Stated percentage does not match the values",
                            explanation=f"The values imply {expected.quantize(Decimal('0.1'))}%, but the document states {percent.comparable_value}%.",
                            confidence=0.9,
                            evidence=(base, current, percent),
                        )
                    )
                    break
                else:
                    continue
                break
    return findings
