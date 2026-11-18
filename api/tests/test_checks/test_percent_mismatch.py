from app.services.checks.percent_mismatch import detect_percent_mismatch
from tests.test_checks.helpers import fact


def _facts(percent: str) -> list:
    return [fact("Acme", "prior revenue", "100"), fact("Acme", "current revenue", "120"), fact("Acme", "revenue growth", percent, unit="%")]


def test_reports_percentage_that_disagrees_with_values() -> None:
    findings = detect_percent_mismatch(_facts("30"))
    assert len(findings) == 1
    assert len(findings[0].evidence) == 3


def test_ignores_percentage_consistent_with_values() -> None:
    assert detect_percent_mismatch(_facts("20")) == []


def test_ignores_percentage_from_different_table_rows() -> None:
    from uuid import uuid4
    table_id = uuid4()
    # Row 1 is Revenue: 100 -> 120 (20%)
    # Row 2 is Operating Income: 50 -> 65, growth is 30%
    facts = [
        fact("Acme", "prior revenue", "100", chunk_type="table", chunk_id=table_id, table_row=1),
        fact("Acme", "current revenue", "120", chunk_type="table", chunk_id=table_id, table_row=1),
        # Here percent is on Row 2 with 30%, which should NOT match Row 1's 100 -> 120
        fact("Acme", "revenue growth", "30", unit="%", chunk_type="table", chunk_id=table_id, table_row=2),
    ]
    assert detect_percent_mismatch(facts) == []
