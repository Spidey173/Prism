from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True)
class FactRecord:
    id: UUID
    chunk_id: UUID
    page_id: UUID
    page_number: int
    subject: str
    metric: str
    value_num: Decimal | None
    value_low: Decimal | None
    value_high: Decimal | None
    unit_normalized: str | None
    period: str | None
    raw_value: str | None
    quote: str
    bboxes: list[list[float]]
    scale: str = "units"
    chunk_type: str = "sentence"
    table_row: int | None = None
    table_col: int | None = None

    @property
    def comparable_value(self) -> Decimal | None:
        if self.value_num is None:
            return None
        multiplier = {"units": 1, "thousands": 1_000, "millions": 1_000_000, "billions": 1_000_000_000}.get(self.scale, 1)
        return self.value_num * Decimal(multiplier)


@dataclass(frozen=True)
class Finding:
    issue_type: str
    detector: str
    severity: str
    title: str
    explanation: str
    confidence: float
    evidence: tuple[FactRecord, ...]
