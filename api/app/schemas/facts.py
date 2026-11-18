from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


ScaleName = Literal["units", "thousands", "millions", "billions"]


class ExtractedFact(BaseModel):
    chunk_ref: UUID
    subject: str = Field(min_length=1)
    metric: str = Field(min_length=1)
    value_num: Decimal | None = None
    value_low: Decimal | None = None
    value_high: Decimal | None = None
    raw_value: str = Field(min_length=1)
    scale: ScaleName = "units"
    unit_normalized: str | None = None
    period: str | None = None
    quote: str = Field(min_length=1)
    table_row: int | None = None
    table_col: int | None = None


class FactExtractionResponse(BaseModel):
    facts: list[ExtractedFact]


class LLMUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: Decimal = Decimal("0")
