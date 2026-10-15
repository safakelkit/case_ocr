# Bu dosya, sayfa kimliği ve güven değeri gibi aşamalar arası ortak veri kurallarını tanımlamak için kullanılır.
"""Small shared schema primitives used by pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class PageIdentity:
    pdf_page_number: int
    page_index: int
    printed_page_number: int | None = None

    def __post_init__(self) -> None:
        if self.pdf_page_number < 1:
            raise ValueError("pdf_page_number must be one-based and positive")
        if self.page_index != self.pdf_page_number - 1:
            raise ValueError("page_index must equal pdf_page_number - 1")


@dataclass(frozen=True)
class BoundingBox:
    left: int
    top: int
    width: int
    height: int

    def __post_init__(self) -> None:
        if min(self.left, self.top, self.width, self.height) < 0:
            raise ValueError("bounding-box values cannot be negative")


@dataclass(frozen=True)
class OcrToken:
    text: str
    bbox: BoundingBox
    confidence: float
    page: PageIdentity
    block_number: int
    paragraph_number: int
    line_number: int
    word_number: int

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("OCR token text cannot be blank")
        validate_confidence(self.confidence)


def validate_confidence(value: float) -> float:
    """Return a finite confidence in the inclusive range [0, 1]."""

    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError("confidence must be a finite float in [0, 1]")
    return value
