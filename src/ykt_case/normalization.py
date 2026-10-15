# Bu dosya, finansal metinleri belge yereline uygun sayısal değerlere ve durumlara dönüştürmek için kullanılır.
"""Locale-aware financial value normalization."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re


class NumericStatus(StrEnum):
    VALUE = "value"
    PERCENTAGE = "percentage"
    PERCENTAGE_RANGE = "percentage_range"
    DASH = "dash"
    BLANK = "blank"
    INVALID = "invalid"


@dataclass(frozen=True)
class ParsedNumber:
    raw: str
    value: int | float | None
    status: NumericStatus


_INTEGER_PATTERN = re.compile(r"^(?:0|[1-9]\d{0,2}(?:\.\d{3})*|[1-9]\d*)$")
_DECIMAL_PATTERN = re.compile(r"^(?:0|[1-9]\d{0,2}(?:\.\d{3})*|[1-9]\d*),\d+$")


def parse_financial_number(raw: str | None) -> ParsedNumber:
    """Parse assignment-specific integer formatting while preserving state."""

    original = "" if raw is None else raw
    text = original.strip()
    if not text:
        return ParsedNumber(raw=original, value=None, status=NumericStatus.BLANK)
    if text in {"-", "–", "—"}:
        return ParsedNumber(raw=original, value=None, status=NumericStatus.DASH)

    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1].strip()

    is_integer = _INTEGER_PATTERN.fullmatch(text) is not None
    is_decimal = _DECIMAL_PATTERN.fullmatch(text) is not None
    if not is_integer and not is_decimal:
        return ParsedNumber(raw=original, value=None, status=NumericStatus.INVALID)

    compact = text.replace(".", "")
    value: int | float
    if is_decimal:
        value = float(compact.replace(",", "."))
    else:
        value = int(compact)
    if negative:
        value = -value
    return ParsedNumber(raw=original, value=value, status=NumericStatus.VALUE)