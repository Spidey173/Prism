from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


@dataclass(frozen=True)
class NormalizedValue:
    value_num: Decimal | None
    value_low: Decimal | None
    value_high: Decimal | None
    raw_value: str
    scale: str
    unit_normalized: str | None


_WORD_NUMBERS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}
_SCALE_WORDS = {"thousand": "thousands", "million": "millions", "billion": "billions"}
_SCALE_SUFFIXES = {"k": "thousands", "m": "millions", "b": "billions"}
_RANGE_SPLIT = re.compile(r"\s+(?:to|through)\s+|(?<=[\w)])\s*[–—-]\s*(?=[\w$€£(])", re.IGNORECASE)


def _word_number(value: str) -> Decimal | None:
    words = re.findall(r"[a-z]+", value.lower())
    if not words:
        return None
    total = 0
    current = 0
    for word in words:
        if word == "and":
            continue
        if word in _WORD_NUMBERS:
            current += _WORD_NUMBERS[word]
        elif word in _SCALE_WORDS:
            current = max(current, 1) * {"thousand": 1_000, "million": 1_000_000, "billion": 1_000_000_000}[word]
            total += current
            current = 0
        else:
            return None
    return Decimal(total + current)


def _scalar(raw: str) -> tuple[Decimal | None, str, str | None]:
    value = raw.strip()
    negative = value.startswith("(") and value.endswith(")")
    if negative:
        value = value[1:-1].strip()
    percent = "%" in value or "percent" in value.lower()
    currency: str | None = None
    if "$" in value or re.search(r"\bUSD\b", value, re.IGNORECASE):
        currency = "USD"
    elif "€" in value or re.search(r"\bEUR\b", value, re.IGNORECASE):
        currency = "EUR"
    elif "£" in value or re.search(r"\bGBP\b", value, re.IGNORECASE):
        currency = "GBP"

    scale = "units"
    suffix_match = re.search(r"\b(thousand|million|billion)s?\b|(?<=\d)([kmb])\b", value, re.IGNORECASE)
    if suffix_match:
        scale = _SCALE_WORDS.get((suffix_match.group(1) or "").lower(), _SCALE_SUFFIXES.get((suffix_match.group(2) or "").lower(), "units"))
    cleaned = re.sub(r"[$€£,%]", "", value)
    cleaned = re.sub(r"\b(?:USD|EUR|GBP|percent|thousands?|millions?|billions?)\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"(?<=\d)[kmb]\b", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = cleaned.replace(",", "")
    try:
        number = Decimal(cleaned)
    except InvalidOperation:
        number = _word_number(cleaned)
    if number is not None and negative:
        number = -abs(number)
    return number, scale, "%" if percent else currency


def normalize_value(raw_value: str, unit_hint: str | None = None) -> NormalizedValue:
    raw = raw_value.strip()
    parts = _RANGE_SPLIT.split(raw, maxsplit=1)
    if len(parts) == 2:
        lower, scale_low, unit_low = _scalar(parts[0])
        upper, scale_high, unit_high = _scalar(parts[1])
        if lower is not None and upper is not None:
            scale = scale_low if scale_low != "units" else scale_high
            if scale_high == "units" and scale_low != "units":
                multiplier = {"thousands": 1_000, "millions": 1_000_000, "billions": 1_000_000_000}[scale]
                upper /= Decimal(multiplier)
            if scale_low == "units" and scale_high != "units":
                multiplier = {"thousands": 1_000, "millions": 1_000_000, "billions": 1_000_000_000}[scale]
                lower /= Decimal(multiplier)
            return NormalizedValue(None, min(lower, upper), max(lower, upper), raw, scale, unit_low or unit_high or unit_hint)

    number, scale, unit = _scalar(raw)
    return NormalizedValue(number, None, None, raw, scale, unit or unit_hint)


def contains_number_or_date(text: str) -> bool:
    if re.search(r"\d", text):
        return True
    lowered = text.lower()
    if re.search(r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\b", lowered):
        return True
    return bool(re.search(r"\b(one|two|three|four|five|six|seven|eight|nine|ten|hundred|thousand|million|billion)\b", lowered))
