from uuid import uuid4

from app.services.checks.sum_mismatch import detect_sum_mismatch
from tests.test_checks.helpers import fact


def test_reports_incorrect_table_total() -> None:
    table_id = uuid4()
    rows = [fact("North", "Revenue", "40", chunk_type="table", chunk_id=table_id), fact("South", "Revenue", "50", chunk_type="table", chunk_id=table_id), fact("Total", "Revenue", "100", chunk_type="table", chunk_id=table_id)]
    assert len(detect_sum_mismatch(rows)) == 1


def test_ignores_correct_total_and_non_table_claims() -> None:
    table_id = uuid4()
    correct = [fact("North", "Revenue", "40", chunk_type="table", chunk_id=table_id), fact("South", "Revenue", "50", chunk_type="table", chunk_id=table_id), fact("Total", "Revenue", "90", chunk_type="table", chunk_id=table_id)]
    prose = [fact("North", "Revenue", "40"), fact("South", "Revenue", "50"), fact("Total", "Revenue", "100")]
    assert detect_sum_mismatch(correct) == []
    assert detect_sum_mismatch(prose) == []


def test_handles_multiple_subtotals_without_false_positives() -> None:
    table_id = uuid4()
    # Structured table with 2 subtotals: Total Current Assets and Total Non-Current Assets
    grid_facts = [
        # Multi-line header with year 2024 at row 1
        fact("Year", "Period", "2024", chunk_type="table", chunk_id=table_id, table_row=1, table_col=1),
        # Current assets section
        fact("Cash", "Revenue", "10", chunk_type="table", chunk_id=table_id, table_row=2, table_col=1),
        fact("Receivables", "Revenue", "20", chunk_type="table", chunk_id=table_id, table_row=3, table_col=1),
        fact("Total Current Assets", "Revenue", "30", chunk_type="table", chunk_id=table_id, table_row=4, table_col=1),
        # Non-current assets section
        fact("Property", "Revenue", "40", chunk_type="table", chunk_id=table_id, table_row=5, table_col=1),
        fact("Equipment", "Revenue", "50", chunk_type="table", chunk_id=table_id, table_row=6, table_col=1),
        fact("Total Non-Current Assets", "Revenue", "90", chunk_type="table", chunk_id=table_id, table_row=7, table_col=1),
    ]
    # In the old code, this would produce false positive errors because it lumped all rows together
    assert detect_sum_mismatch(grid_facts) == []


def test_reports_error_in_specific_subtotal_block() -> None:
    table_id = uuid4()
    grid_facts = [
        # Correct first block: 10 + 20 = 30
        fact("Cash", "Revenue", "10", chunk_type="table", chunk_id=table_id, table_row=1, table_col=1),
        fact("Receivables", "Revenue", "20", chunk_type="table", chunk_id=table_id, table_row=2, table_col=1),
        fact("Total Current Assets", "Revenue", "30", chunk_type="table", chunk_id=table_id, table_row=3, table_col=1),
        # Erroneous second block: 40 + 50 = 90, but total stated as 100
        fact("Property", "Revenue", "40", chunk_type="table", chunk_id=table_id, table_row=4, table_col=1),
        fact("Equipment", "Revenue", "50", chunk_type="table", chunk_id=table_id, table_row=5, table_col=1),
        fact("Total Non-Current Assets", "Revenue", "100", chunk_type="table", chunk_id=table_id, table_row=6, table_col=1),
    ]
    findings = detect_sum_mismatch(grid_facts)
    assert len(findings) == 1
    assert "Total Non-Current Assets" in [e.subject for e in findings[0].evidence]
