from app.services.checks.date_order import detect_date_order
from tests.test_checks.helpers import fact


def test_reports_end_before_start() -> None:
    findings = detect_date_order([
        fact("Project A", "start date", None, unit="date", raw="2025-05-01"),
        fact("Project A", "end date", None, unit="date", raw="2025-04-30"),
    ])
    assert len(findings) == 1
    assert len(findings[0].evidence) == 2


def test_ignores_valid_date_order() -> None:
    assert detect_date_order([
        fact("Project A", "start date", None, unit="date", raw="2025-04-30"),
        fact("Project A", "end date", None, unit="date", raw="2025-05-01"),
    ]) == []
