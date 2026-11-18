from decimal import Decimal

import pytest

from app.services.value_normalization import normalize_value


@pytest.mark.parametrize(
    ("raw", "number", "scale", "unit"),
    [
        ("$1.5M", Decimal("1.5"), "millions", "USD"),
        ("12.5%", Decimal("12.5"), "units", "%"),
        ("(3,200)", Decimal("-3200"), "units", None),
        ("two million", Decimal("2"), "millions", None),
        ("3,200", Decimal("3200"), "units", None),
    ],
)
def test_normalize_scalar_values(raw: str, number: Decimal, scale: str, unit: str | None) -> None:
    normalized = normalize_value(raw)
    assert normalized.value_num == number
    assert normalized.scale == scale
    assert normalized.unit_normalized == unit


def test_normalize_range_with_shared_scale() -> None:
    normalized = normalize_value("$1.5M-$2M")
    assert normalized.value_num is None
    assert normalized.value_low == Decimal("1.5")
    assert normalized.value_high == Decimal("2")
    assert normalized.scale == "millions"
    assert normalized.unit_normalized == "USD"
