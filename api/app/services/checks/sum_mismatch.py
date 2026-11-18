from collections import defaultdict
from decimal import Decimal
from uuid import UUID

from app.services.checks.types import FactRecord, Finding


def _normal(value: str) -> str:
    return " ".join(value.casefold().replace("total", "").split())


def _is_year_or_period_label(fact: FactRecord) -> bool:
    val = fact.comparable_value
    if val is None:
        return False
    is_year_range = Decimal(1990) <= val <= Decimal(2100) and val % 1 == 0
    metric_lower = fact.metric.casefold()
    subject_lower = fact.subject.casefold()
    if is_year_range and any(word in metric_lower or word in subject_lower for word in ("year", "period", "fy", "ended")):
        return True
    return False


def detect_sum_mismatch(facts: list[FactRecord], tolerance: Decimal = Decimal("0.01")) -> list[Finding]:
    tables: dict[object, list[FactRecord]] = defaultdict(list)
    for fact in facts:
        if fact.chunk_type == "table" and fact.comparable_value is not None:
            tables[fact.chunk_id].append(fact)

    findings: list[Finding] = []
    for table_facts in tables.values():
        has_grid = any(f.table_row is not None and f.table_col is not None for f in table_facts)
        if has_grid:
            # Group by column index to isolate vertical arithmetic relationships
            by_col: dict[int, list[FactRecord]] = defaultdict(list)
            for fact in table_facts:
                col = fact.table_col if fact.table_col is not None else 0
                by_col[col].append(fact)

            for col_facts in by_col.values():
                col_facts.sort(key=lambda f: f.table_row if f.table_row is not None else 0)
                contiguous_parts: list[FactRecord] = []
                for fact in col_facts:
                    is_total = "total" in fact.subject.casefold() or "total" in fact.metric.casefold()
                    if is_total:
                        if len(contiguous_parts) >= 2:
                            sum_value = sum((p.comparable_value or Decimal(0) for p in contiguous_parts), Decimal(0))
                            total_value = fact.comparable_value or Decimal(0)
                            allowed_tol = max(tolerance, abs(total_value) * Decimal("0.005"))
                            if abs(total_value - sum_value) > allowed_tol:
                                findings.append(
                                    Finding(
                                        issue_type="sum_mismatch",
                                        detector="sum_mismatch",
                                        severity="high",
                                        title=f"Table total does not match {fact.metric or 'its parts'}",
                                        explanation=f"The listed parts sum to {sum_value}, but the stated total is {total_value}.",
                                        confidence=0.98,
                                        evidence=tuple([*contiguous_parts, fact]),
                                    )
                                )
                        contiguous_parts = []
                    else:
                        if not _is_year_or_period_label(fact):
                            contiguous_parts.append(fact)
        else:
            by_metric: dict[str, list[FactRecord]] = defaultdict(list)
            for fact in table_facts:
                by_metric[_normal(fact.metric)].append(fact)
            for metric, metric_facts in by_metric.items():
                totals = [fact for fact in metric_facts if "total" in fact.subject.casefold() or "total" in fact.metric.casefold()]
                parts = [fact for fact in metric_facts if fact not in totals and not _is_year_or_period_label(fact)]
                if not totals or len(parts) < 2:
                    continue
                for total in totals:
                    sum_value = sum((part.comparable_value or Decimal(0) for part in parts), Decimal(0))
                    total_value = total.comparable_value or Decimal(0)
                    allowed_tol = max(tolerance, abs(total_value) * Decimal("0.005"))
                    if abs(total_value - sum_value) <= allowed_tol:
                        continue
                    findings.append(
                        Finding(
                            issue_type="sum_mismatch",
                            detector="sum_mismatch",
                            severity="high",
                            title=f"Table total does not match {metric or 'its parts'}",
                            explanation=f"The listed parts sum to {sum_value}, but the stated total is {total_value}.",
                            confidence=0.98,
                            evidence=tuple([*parts, total]),
                        )
                    )
    return findings
