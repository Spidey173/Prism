from app.services.checks.same_metric_conflict import detect_same_metric_conflict
from tests.test_checks.helpers import fact


def test_reports_different_values_for_same_period() -> None:
    results = detect_same_metric_conflict([
        fact("Acme", "revenue", "100", period="2025"),
        fact("Acme", "revenue", "120", page=2, period="2025"),
    ])
    assert len(results) == 1
    assert len(results[0].evidence) == 2


def test_ignores_matching_values_and_different_periods() -> None:
    assert detect_same_metric_conflict([
        fact("Acme", "revenue", "100", period="2024"),
        fact("Acme", "revenue", "100.2", period="2024"),
        fact("Acme", "revenue", "120", period="2025"),
    ]) == []
