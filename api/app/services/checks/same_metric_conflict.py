from collections import defaultdict
from decimal import Decimal

from app.services.checks.types import FactRecord, Finding


def _key(value: str | None) -> str:
    return " ".join((value or "").casefold().split())


def _different(left: FactRecord, right: FactRecord) -> bool:
    left_value = left.comparable_value
    right_value = right.comparable_value
    if left_value is None or right_value is None:
        return False
    tolerance = max(Decimal("0.01"), max(abs(left_value), abs(right_value)) * Decimal("0.005"))
    return abs(left_value - right_value) > tolerance


def detect_same_metric_conflict(facts: list[FactRecord]) -> list[Finding]:
    groups: dict[tuple[str, str, str], list[FactRecord]] = defaultdict(list)
    for fact in facts:
        if fact.comparable_value is not None:
            groups[(_key(fact.subject), _key(fact.metric), _key(fact.period))].append(fact)

    findings: list[Finding] = []
    for (_subject, metric, period), items in groups.items():
        distinct: list[FactRecord] = []
        for fact in items:
            if not distinct:
                distinct.append(fact)
            elif len(distinct) == 1 and _different(fact, distinct[0]):
                distinct.append(fact)
        if len(distinct) < 2:
            continue
        first, second = distinct[0], distinct[1]
        findings.append(
            Finding(
                issue_type="same_metric_conflict",
                detector="same_metric_conflict",
                severity="high",
                title=f"Conflicting values for {first.metric}",
                explanation=(
                    f"The document reports {first.raw_value or first.comparable_value} and {second.raw_value or second.comparable_value} for the same "
                    f"metric{f' in {period}' if period else ''}."
                ),
                confidence=0.98,
                evidence=(first, second),
            )
        )
    return findings
