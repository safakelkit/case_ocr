# Bu dosya, yapılandırılmış dipnot numaralarını önceden bilinen sayfa veya başlık kullanmadan bulmak için kullanılır.
"""Locate configured disclosure notes without known page numbers or titles."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import re
import statistics
import unicodedata
from typing import Any

from ykt_case.schemas import OcrToken


_HEADING_PATTERN = re.compile(
    r"^\s*(?P<number>\d{1,3})\s*[.)]\s+(?P<title>.+?)\s*$"
)


@dataclass(frozen=True)
class HeadingCandidate:
    pdf_page_number: int
    detected_number: int
    raw_text: str
    title: str
    normalized_title: str
    is_continuation: bool
    confidence: float
    bbox: dict[str, int]


def _normalize_title(text: str) -> str:
    without_continuation = re.sub(r"\([^)]*devam[^)]*\)", " ", text, flags=re.IGNORECASE)
    casefolded = without_continuation.casefold().replace("ı", "i")
    decomposed = unicodedata.normalize("NFKD", casefolded)
    plain = "".join(character for character in decomposed if not unicodedata.combining(character))
    return " ".join(re.findall(r"[a-z0-9]+", plain))


def _bbox(tokens: list[OcrToken]) -> dict[str, int]:
    left = min(token.bbox.left for token in tokens)
    top = min(token.bbox.top for token in tokens)
    right = max(token.bbox.left + token.bbox.width for token in tokens)
    bottom = max(token.bbox.top + token.bbox.height for token in tokens)
    return {"left": left, "top": top, "width": right - left, "height": bottom - top}


def _uppercase_ratio(text: str) -> float:
    letters = [character for character in text if character.isalpha()]
    if not letters:
        return 0.0
    return sum(character.isupper() for character in letters) / len(letters)


def _financial_fragment_count(text: str) -> int:
    return len(re.findall(r"(?<!\w)\(?\d[\d.]*\)?", text))


def extract_heading_candidates(tokens: list[OcrToken]) -> list[HeadingCandidate]:
    """Extract numbered, heading-like OCR lines from one page."""

    groups: dict[tuple[int, int, int], list[OcrToken]] = {}
    for token in tokens:
        key = (token.block_number, token.paragraph_number, token.line_number)
        groups.setdefault(key, []).append(token)

    candidates: list[HeadingCandidate] = []
    for group in groups.values():
        ordered = sorted(group, key=lambda token: token.bbox.left)
        raw_text = " ".join(token.text for token in ordered)
        match = _HEADING_PATTERN.fullmatch(raw_text)
        if match is None:
            continue
        title = match.group("title").strip()
        title_without_continuation = re.sub(
            r"\([^)]*devam[^)]*\)", " ", title, flags=re.IGNORECASE
        )
        if _uppercase_ratio(title_without_continuation) < 0.70:
            continue
        if _financial_fragment_count(title) >= 2:
            continue
        normalized_title = _normalize_title(title)
        if not normalized_title:
            continue
        candidates.append(
            HeadingCandidate(
                pdf_page_number=ordered[0].page.pdf_page_number,
                detected_number=int(match.group("number")),
                raw_text=raw_text,
                title=title,
                normalized_title=normalized_title,
                is_continuation="devam" in title.casefold(),
                confidence=round(
                    statistics.fmean(token.confidence for token in ordered), 6
                ),
                bbox=_bbox(ordered),
            )
        )
    return candidates


def _similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, left, right).ratio()


def locate_target_notes(
    candidates: list[HeadingCandidate],
    target_notes: tuple[int, ...],
) -> list[dict[str, Any]]:
    """Locate targets and recover a corrupted first page from a verified continuation."""

    ordered = sorted(candidates, key=lambda item: (item.pdf_page_number, item.bbox["top"]))
    results: list[dict[str, Any]] = []
    for target in target_notes:
        exact = [candidate for candidate in ordered if candidate.detected_number == target]
        if not exact:
            raise ValueError(f"configured note {target} was not found in document scan")
        anchor = max(exact, key=lambda candidate: candidate.confidence)
        matching_exact = [
            candidate
            for candidate in exact
            if _similarity(candidate.normalized_title, anchor.normalized_title) >= 0.80
        ]
        non_continuation = [
            candidate for candidate in matching_exact if not candidate.is_continuation
        ]
        if non_continuation:
            anchor = max(non_continuation, key=lambda candidate: candidate.confidence)
        pages = {candidate.pdf_page_number for candidate in matching_exact}
        evidence: list[dict[str, Any]] = [
            {
                "kind": "exact_heading",
                "pdf_page_number": candidate.pdf_page_number,
                "raw_text": candidate.raw_text,
                "confidence": candidate.confidence,
            }
            for candidate in matching_exact
        ]
        recovered = False
        recovery_similarity: float | None = None
        if anchor.is_continuation:
            previous_page = anchor.pdf_page_number - 1
            previous_candidates = [
                candidate for candidate in ordered if candidate.pdf_page_number == previous_page
            ]
            if previous_candidates:
                previous = max(
                    previous_candidates,
                    key=lambda candidate: _similarity(
                        candidate.normalized_title, anchor.normalized_title
                    ),
                )
                recovery_similarity = _similarity(
                    previous.normalized_title, anchor.normalized_title
                )
                if recovery_similarity >= 0.80:
                    pages.add(previous.pdf_page_number)
                    recovered = True
                    evidence.append(
                        {
                            "kind": "recovered_corrupt_heading_number",
                            "pdf_page_number": previous.pdf_page_number,
                            "detected_number": previous.detected_number,
                            "raw_text": previous.raw_text,
                            "title_similarity": round(recovery_similarity, 6),
                            "confidence": previous.confidence,
                        }
                    )
        exact_confidence = statistics.fmean(
            candidate.confidence for candidate in matching_exact
        )
        sequence_evidence = recovery_similarity if recovered else 1.0
        location_confidence = round(
            statistics.fmean([exact_confidence, sequence_evidence]), 6
        )
        results.append(
            {
                "note_number": target,
                "status": "located_with_recovery" if recovered else "located",
                "title": anchor.title,
                "pdf_pages": sorted(pages),
                "confidence": location_confidence,
                "evidence": evidence,
            }
        )
    return results
