from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class SemanticPairInput(BaseModel):
    pair_hash: str
    chunk_a: UUID
    page_a: int
    quote_a: str
    chunk_b: UUID
    page_b: int
    quote_b: str


class PairJudgment(BaseModel):
    pair_hash: str = Field(min_length=64, max_length=64)
    verdict: Literal["contradiction", "consistent", "unrelated"]
    reason: str = Field(min_length=1, max_length=800)
    confidence: float = Field(ge=0, le=1)
    conflicting_span_a: str | None = None
    conflicting_span_b: str | None = None


class SemanticJudgmentBatch(BaseModel):
    judgments: list[PairJudgment]
