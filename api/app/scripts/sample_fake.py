from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel


def _payload(prompt: str, tag: str) -> dict[str, Any]:
    opening = f"<{tag}>\n"
    start = prompt.rfind(opening)
    if start < 0:
        return {}
    start += len(opening)
    end = prompt.find(f"\n</{tag}>", start)
    if end < 0:
        return {}
    value = json.loads(prompt[start:end])
    return value if isinstance(value, dict) else {}


def _fact(chunk_ref: str, subject: str, metric: str, raw_value: str, quote: str, **extra: Any) -> dict[str, Any]:
    return {
        "chunk_ref": chunk_ref,
        "subject": subject,
        "metric": metric,
        "raw_value": raw_value,
        "quote": quote,
        **extra,
    }


def _extract_sentence_facts(item: dict[str, Any]) -> list[dict[str, Any]]:
    text = str(item.get("text", ""))
    chunk_ref = str(item.get("chunk_ref", ""))
    facts: list[dict[str, Any]] = []
    revenue = re.search(r"Acme reported revenue of (\$[\d,.]+[KMB]?) in (FY\d{4})", text, re.IGNORECASE)
    if revenue:
        facts.append(_fact(chunk_ref, "Acme", "revenue", revenue.group(1), text, period=revenue.group(2)))
    for metric, pattern in (
        ("prior revenue", r"prior revenue was ([\d,.]+)"),
        ("current revenue", r"current revenue is ([\d,.]+)"),
        ("revenue growth", r"revenue growth is ([\d,.]+%)"),
    ):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            raw = match.group(1)
            facts.append(_fact(chunk_ref, "Acme", metric, raw, text, unit_normalized="%" if "%" in raw else None))
    for metric in ("start date", "end date"):
        match = re.search(rf"Project {metric}: ([A-Za-z]+ \d{{1,2}}, \d{{4}})", text, re.IGNORECASE)
        if match:
            facts.append(_fact(chunk_ref, "Project A", metric, match.group(1), text, unit_normalized="date"))
    return facts


def _extract_table_facts(item: dict[str, Any]) -> list[dict[str, Any]]:
    cells = item.get("cells", [])
    if not isinstance(cells, list):
        return []
    by_position = {
        (cell.get("row"), cell.get("col")): str(cell.get("text", "")).strip()
        for cell in cells if isinstance(cell, dict)
    }
    rows = [row for row, _column in by_position if isinstance(row, int)]
    columns = [column for _row, column in by_position if isinstance(column, int)]
    header_row = item.get("header_row")
    if not isinstance(header_row, int):
        header_row = min(rows, default=0)
    first_column = min(columns, default=0)
    facts = []
    for row in sorted(set(rows)):
        if row <= header_row:
            continue
        subject = by_position.get((row, first_column), "")
        for column in sorted(set(columns)):
            raw = by_position.get((row, column), "")
            if column == first_column or not re.search(r"\d", raw):
                continue
            metric = by_position.get((header_row, column), "value")
            quote = f"{subject}: {metric} {raw}"
            facts.append(
                _fact(
                    str(item.get("chunk_ref", "")), subject, metric, raw, quote,
                    table_row=row, table_col=column,
                )
            )
    return facts


def sample_fake_response(prompt: str, schema: type[BaseModel]) -> dict[str, Any]:
    if schema.__name__ == "FactExtractionResponse":
        payload = _payload(prompt, "document_data")
        facts: list[dict[str, Any]] = []
        for item in payload.get("sentences", []):
            if isinstance(item, dict):
                facts.extend(_extract_sentence_facts(item))
        table = payload.get("table")
        if isinstance(table, dict):
            facts.extend(_extract_table_facts(table))
        return {"facts": facts}

    if schema.__name__ == "SemanticJudgmentBatch":
        payload = _payload(prompt, "untrusted_pairs")
        judgments = []
        for pair in payload.get("pairs", []):
            if not isinstance(pair, dict):
                continue
            quote_a = str(pair.get("quote_a", ""))
            quote_b = str(pair.get("quote_b", ""))
            joined = f"{quote_a} {quote_b}".casefold()
            verdict, reason, span_a, span_b, confidence = "unrelated", "The statements concern different details and do not conflict.", None, None, 0.96
            if "renewed" in joined and ("cannot be renewed" in joined or "may not be renewed" in joined):
                verdict = "contradiction"
                reason = "One sentence permits renewal, while the other expressly prohibits renewal after the initial term."
                if "may be renewed" in quote_a:
                    span_a, span_b = "may be renewed", "cannot be renewed"
                else:
                    span_a, span_b = "cannot be renewed", "may be renewed"
                confidence = 0.98
            elif "written notice" in joined and "without giving any prior notice" in joined:
                verdict = "contradiction"
                reason = "One sentence requires prior written notice, while the other allows termination without notice."
                if "must give written notice" in quote_a:
                    span_a, span_b = "must give written notice", "without giving any prior notice"
                else:
                    span_a, span_b = "without giving any prior notice", "must give written notice"
                confidence = 0.97
            elif "support plan" in joined and "renew" in joined and "cancel" in joined:
                verdict, reason, confidence = "consistent", "Automatic renewal can coexist with a customer's right to cancel.", 0.94
            judgments.append({
                "pair_hash": pair.get("pair_hash"),
                "verdict": verdict,
                "reason": reason,
                "confidence": confidence,
                "conflicting_span_a": span_a,
                "conflicting_span_b": span_b,
            })
        return {"judgments": judgments}

    return {}
