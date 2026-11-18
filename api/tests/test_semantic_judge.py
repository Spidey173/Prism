from decimal import Decimal
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.schemas.semantic import SemanticJudgmentBatch
from app.services.cost_control import AuditCostLimitReached, BudgetedLLMClient
from app.services.llm import FakeLLMClient
from app.services.semantic_audit import judge_batch
from app.services.semantic_candidates import CandidateClaim, CandidatePair


def _pair() -> CandidatePair:
    left = CandidateClaim(uuid4(), 1, 1, uuid4(), "The service agreement may be renewed annually after the initial term.")
    right = CandidateClaim(uuid4(), 2, 1, uuid4(), "The service agreement cannot be renewed after the initial term.")
    return CandidatePair(left, right, 0.91)


@pytest.mark.parametrize("verdict", ["contradiction", "consistent", "unrelated"])
def test_fake_llm_validates_each_judgment(verdict: str) -> None:
    pair = _pair()
    from app.services.semantic_audit import pair_text_hash

    response = {"judgments": [{"pair_hash": pair_text_hash(pair.left.text, pair.right.text), "verdict": verdict, "reason": "A concise judge reason.", "confidence": 0.91, "conflicting_span_a": None, "conflicting_span_b": None}]}
    judged = judge_batch(FakeLLMClient([response]), [pair])
    assert isinstance(judged, SemanticJudgmentBatch)
    assert judged.judgments[0].verdict == verdict


def test_fake_llm_retries_invalid_json_then_validates() -> None:
    pair = _pair()
    from app.services.semantic_audit import pair_text_hash

    valid = {"judgments": [{"pair_hash": pair_text_hash(pair.left.text, pair.right.text), "verdict": "contradiction", "reason": "The claims cannot both hold.", "confidence": 0.95}]}
    judged = judge_batch(FakeLLMClient(["not json", valid]), [pair])
    assert judged.judgments[0].verdict == "contradiction"


def test_cost_cap_stops_before_call() -> None:
    fake = FakeLLMClient([{"judgments": []}])
    settings = Settings(
        llm_input_usd_per_million=Decimal("100"),
        llm_output_usd_per_million=Decimal("0"),
        llm_max_cost_per_audit_usd=Decimal("0.000001"),
    )
    budgeted = BudgetedLLMClient(fake, settings, lambda: Decimal(0))
    with pytest.raises(AuditCostLimitReached):
        budgeted.complete_json("system", "a" * 100, SemanticJudgmentBatch)
    assert fake.calls == 0
