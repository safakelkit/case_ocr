# Bu dosya, özet tablo satırlarıyla dipnot satırlarını açıklanabilir baseline yöntemle eşlemek için kullanılır.
"""Explainable baseline relation matching for summary and disclosure-note rows."""

from __future__ import annotations

from difflib import SequenceMatcher
import re
import statistics
import unicodedata
from typing import Any


def _normalize_text(text: str | None) -> str:
    if not text:
        return ""
    casefolded = text.casefold().replace("ı", "i")
    decomposed = unicodedata.normalize("NFKD", casefolded)
    plain = "".join(character for character in decomposed if not unicodedata.combining(character))
    return " ".join(re.findall(r"[a-z0-9]+", plain))


def _lexical_similarity(left: str | None, right: str | None) -> dict[str, float]:
    normalized_left = _normalize_text(left)
    normalized_right = _normalize_text(right)
    if not normalized_left or not normalized_right:
        return {"sequence": 0.0, "token_jaccard": 0.0, "combined": 0.0}
    sequence = SequenceMatcher(None, normalized_left, normalized_right).ratio()
    left_tokens = set(normalized_left.split())
    right_tokens = set(normalized_right.split())
    union = left_tokens | right_tokens
    jaccard = len(left_tokens & right_tokens) / len(union) if union else 0.0
    return {
        "sequence": round(sequence, 6),
        "token_jaccard": round(jaccard, 6),
        "combined": round(max(sequence, jaccard), 6),
    }


def _summary_values(row: dict[str, Any]) -> list[dict[str, Any]]:
    data_cells = [
        cell
        for cell in row.get("cells", [])
        if cell.get("role") == "data_cell"
        and cell.get("numeric_status") == "value"
        and cell.get("normalized_value") is not None
    ]
    return [
        {
            "index": index,
            "period": cell.get("period"),
            "value": cell.get("normalized_value"),
            "raw_text": cell.get("raw_text"),
        }
        for index, cell in enumerate(data_cells)
    ]


def _note_values(row: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "cell_position": cell_position,
            "column_index": int(cell["column_index"]),
            "column_header": cell.get("column_header"),
            "value": cell.get("normalized_value"),
            "raw_text": cell.get("raw_text"),
        }
        for cell_position, cell in enumerate(row.get("cells", []))
        if cell.get("numeric_status") == "value"
        and cell.get("normalized_value") is not None
    ]


def _structural_compatibility(summary_label: str | None, note_row_type: str | None) -> float:
    normalized = _normalize_text(summary_label)
    transactional_terms = {
        "fark",
        "gelir",
        "gider",
        "maliyet",
        "kar",
        "zarar",
        "kazanc",
    }
    has_transactional_term = any(
        token.startswith(term)
        for token in normalized.split()
        for term in transactional_terms
    )
    expected = "detail" if has_transactional_term else "total"
    return 1.0 if note_row_type == expected else 0.5


def _candidate(
    summary_table: dict[str, Any],
    summary_row: dict[str, Any],
    note_table: dict[str, Any],
    note_row: dict[str, Any],
) -> dict[str, Any]:
    summary_values = _summary_values(summary_row)
    note_values = _note_values(note_row)
    matches: list[dict[str, Any]] = []
    matched_indices: set[int] = set()
    consumed_note_cells: set[int] = set()
    for summary_value in summary_values:
        matching_note_cells = [
            note_value
            for note_value in note_values
            if note_value["value"] == summary_value["value"]
            and int(note_value["cell_position"]) not in consumed_note_cells
        ]
        if not matching_note_cells:
            continue
        period = str(summary_value.get("period") or "")
        period_aligned = [
            note_value
            for note_value in matching_note_cells
            if period and period in str(note_value.get("column_header") or "")
        ]
        chosen = (period_aligned or matching_note_cells)[0]
        consumed_note_cells.add(int(chosen["cell_position"]))
        matched_indices.add(int(summary_value["index"]))
        matches.append(
            {
                "summary_period": summary_value["period"],
                "summary_raw_text": summary_value["raw_text"],
                "normalized_value": summary_value["value"],
                "note_cells": [
                    {
                        key: value
                        for key, value in chosen.items()
                        if key != "cell_position"
                    }
                ],
            }
        )
    numeric_coverage = (
        len(matched_indices) / len(summary_values) if summary_values else 0.0
    )
    lexical = _lexical_similarity(summary_row.get("label"), note_row.get("label"))
    structural_compatibility = _structural_compatibility(
        summary_row.get("label"), note_row.get("row_type")
    )
    evidence_quality = statistics.fmean(
        [
            float(summary_row.get("confidence", 0.0)),
            float(note_row.get("confidence", 0.0)),
            float(note_table.get("confidence", 0.0)),
        ]
    )
    score = round(
        0.50 * numeric_coverage
        + 0.25 * lexical["combined"]
        + 0.10 * structural_compatibility
        + 0.15 * evidence_quality,
        6,
    )
    summary_row_id = str(
        summary_row.get("row_id")
        or f"{summary_table['table_id']}:row-{summary_row['row_index']}"
    )
    note_row_id = str(
        note_row.get("row_id")
        or f"{note_table['table_id']}:row-{note_row['row_index']}"
    )
    return {
        "candidate_id": f"{summary_row_id}--{note_row_id}",
        "note_row_id": note_row_id,
        "note_table_id": note_table["table_id"],
        "note_page_number": int(note_table["page"]["pdf_page_number"]),
        "note_row_index": int(note_row["row_index"]),
        "note_row_label": note_row.get("label"),
        "note_row_type": note_row.get("row_type"),
        "score": score,
        "features": {
            "lexical": lexical,
            "numeric_coverage": round(numeric_coverage, 6),
            "matched_summary_value_indices": sorted(matched_indices),
            "matched_values": matches,
            "structural_compatibility": structural_compatibility,
            "evidence_quality": round(evidence_quality, 6),
        },
        "evidence": {
            "summary_source": summary_row.get("source"),
            "note_source": note_row.get("source"),
        },
    }


def _select_covering_candidates(
    candidates: list[dict[str, Any]],
    summary_value_count: int,
    minimum_score: float,
) -> tuple[list[dict[str, Any]], set[int]]:
    uncovered = set(range(summary_value_count))
    selected: list[dict[str, Any]] = []
    remaining = list(candidates)
    while uncovered:
        useful = [
            candidate
            for candidate in remaining
            if candidate["score"] >= minimum_score
            and uncovered.intersection(
                candidate["features"]["matched_summary_value_indices"]
            )
        ]
        if not useful:
            break
        best = max(
            useful,
            key=lambda candidate: (
                len(
                    uncovered.intersection(
                        candidate["features"]["matched_summary_value_indices"]
                    )
                ),
                candidate["score"],
            ),
        )
        selected.append(best)
        uncovered.difference_update(
            best["features"]["matched_summary_value_indices"]
        )
        remaining.remove(best)
    return selected, uncovered


def _referenced_target_notes(
    raw_reference: Any, target_notes: tuple[int, ...]
) -> tuple[int, ...]:
    """Return configured note numbers without dropping multi-reference cells."""

    if raw_reference is None:
        return ()
    configured = set(target_notes)
    parsed = [int(value) for value in re.findall(r"\d+", str(raw_reference))]
    return tuple(dict.fromkeys(value for value in parsed if value in configured))


def _baseline_relation_for_note(
    summary_table: dict[str, Any],
    summary_row: dict[str, Any],
    note: dict[str, Any],
    note_number: int,
    top_k: int,
    minimum_candidate_score: float,
) -> dict[str, Any]:
    summary_values = _summary_values(summary_row)
    if not summary_values:
        raise ValueError(
            f"summary row {summary_table['table_id']}:{summary_row['row_index']} "
            "has no valid numeric values for relation matching"
        )
    candidates = [
        _candidate(summary_table, summary_row, note_table, note_row)
        for note_table in note.get("tables", [])
        for note_row in note_table.get("rows", [])
    ]
    candidates.sort(key=lambda candidate: candidate["score"], reverse=True)
    selected, uncovered = _select_covering_candidates(
        candidates,
        summary_value_count=len(summary_values),
        minimum_score=minimum_candidate_score,
    )
    coverage = 1.0 - len(uncovered) / len(summary_values)
    relation_confidence = (
        round(
            0.70 * statistics.fmean(candidate["score"] for candidate in selected)
            + 0.30 * coverage,
            6,
        )
        if selected
        else 0.0
    )
    status = (
        "matched"
        if coverage == 1.0
        else "partial_match"
        if coverage > 0.0
        else "abstained"
    )
    numeric_alternatives = [
        candidate
        for candidate in candidates
        if candidate["features"]["numeric_coverage"] > 0.0
    ]
    summary_row_id = str(
        summary_row.get("row_id")
        or f"{summary_table['table_id']}:row-{summary_row['row_index']}"
    )
    return {
        "relation_id": f"baseline:{summary_row_id}:note-{note_number}",
        "method": "lexical_numeric_structural_baseline",
        "summary_row_id": summary_row_id,
        "summary_table_id": summary_table["table_id"],
        "summary_page_number": int(summary_table["page"]["pdf_page_number"]),
        "summary_row_index": int(summary_row["row_index"]),
        "summary_label": summary_row.get("label"),
        "note_number": note_number,
        "status": status,
        "selected_note_row_ids": [candidate["note_row_id"] for candidate in selected],
        "matched_value_coverage": round(coverage, 6),
        "unmatched_periods": [
            summary_values[index]["period"] for index in sorted(uncovered)
        ],
        "ambiguous": len(numeric_alternatives) > len(selected),
        "confidence": relation_confidence,
        "top_candidates": candidates[:top_k],
    }


def match_relations_baseline(
    summary_output: dict[str, Any],
    note_output: dict[str, Any],
    target_notes: tuple[int, ...],
    top_k: int,
    minimum_candidate_score: float,
) -> dict[str, Any]:
    """Generate and rank candidates for every summary row referencing a target note."""

    notes_by_number = {
        int(note["note_number"]): note for note in note_output.get("notes", [])
    }
    relations: list[dict[str, Any]] = []
    for summary_table in summary_output.get("tables", []):
        for summary_row in summary_table.get("rows", []):
            for note_number in _referenced_target_notes(
                summary_row.get("note_reference"), target_notes
            ):
                note = notes_by_number.get(note_number)
                if note is None:
                    raise ValueError(
                        f"structured note output is missing configured note {note_number}"
                    )
                relations.append(
                    _baseline_relation_for_note(
                        summary_table,
                        summary_row,
                        note,
                        note_number,
                        top_k,
                        minimum_candidate_score,
                    )
                )
    if not relations:
        raise ValueError("no summary rows reference the configured target notes")
    statuses = {relation["status"] for relation in relations}
    overall_status = (
        "completed"
        if statuses == {"matched"}
        else "completed_with_warnings"
        if "matched" in statuses or "partial_match" in statuses
        else "failed"
    )
    return {
        "stage": "relation_matching_baseline",
        "status": overall_status,
        "method": {
            "name": "lexical_numeric_structural_baseline",
            "weights": {
                "numeric_coverage": 0.50,
                "lexical_similarity": 0.25,
                "structural_compatibility": 0.10,
                "evidence_quality": 0.15,
            },
            "minimum_candidate_score": minimum_candidate_score,
            "top_k": top_k,
        },
        "relations": relations,
    }