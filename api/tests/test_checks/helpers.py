from decimal import Decimal
from uuid import UUID, uuid4

from app.services.checks.types import FactRecord


def fact(subject: str, metric: str, value: str | None, *, page: int = 1, period: str | None = None,
         unit: str | None = None, raw: str | None = None, chunk_type: str = "sentence",
         chunk_id: UUID | None = None, table_row: int | None = None, table_col: int | None = None) -> FactRecord:
    return FactRecord(
        id=uuid4(), chunk_id=chunk_id or uuid4(), page_id=uuid4(), page_number=page,
        subject=subject, metric=metric, value_num=Decimal(value) if value is not None else None,
        value_low=None, value_high=None, unit_normalized=unit, period=period,
        raw_value=raw, quote=f"{subject} {metric} {raw or value}", bboxes=[[0.1, 0.1, 0.3, 0.2]],
        chunk_type=chunk_type, table_row=table_row, table_col=table_col,
    )
