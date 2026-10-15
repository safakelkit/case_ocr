# Bu dosya, bulunan dipnot sayfalarındaki tabloları OCR geometrisinden yapılandırılmış satır ve hücrelere dönüştürmek için kullanılır.
"""Geometry-based extraction of tables inside located disclosure-note pages."""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
import statistics
from typing import Any

from ykt_case.normalization import NumericStatus, parse_financial_number


_NUMERICISH_PATTERN = re.compile(
    r"^[^\w%]*%?\(?\d[\d.,%()\-–—]*\)?[^\w%]*$"
)
_PERCENT_PATTERN = re.compile(r"^%?\s*(\d+(?:,\d+)?)$")
_PERCENT_RANGE_PATTERN = re.compile(
    r"^%\s*(\d+(?:,\d+)?)\s*[-–—]\s*%?\s*(\d+(?:,\d+)?)$"
)


@dataclass(frozen=True)
class _VisualRow:
    tokens: tuple[dict[str, Any], ...]
    center_y: float


def _token_center_x(token: dict[str, Any]) -> float:
    return float(token["bbox"]["left"]) + float(token["bbox"]["width"]) / 2


def _token_center_y(token: dict[str, Any]) -> float:
    return float(token["bbox"]["top"]) + float(token["bbox"]["height"]) / 2


def _token_right(token: dict[str, Any]) -> int:
    return int(token["bbox"]["left"]) + int(token["bbox"]["width"])


def _token_bottom(token: dict[str, Any]) -> int:
    return int(token["bbox"]["top"]) + int(token["bbox"]["height"])


def _bbox(tokens: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> dict[str, int] | None:
    if not tokens:
        return None
    left = min(int(token["bbox"]["left"]) for token in tokens)
    top = min(int(token["bbox"]["top"]) for token in tokens)
    right = max(_token_right(token) for token in tokens)
    bottom = max(_token_bottom(token) for token in tokens)
    return {"left": left, "top": top, "width": right - left, "height": bottom - top}


def _confidence(tokens: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> float:
    if not tokens:
        return 0.0
    return round(statistics.fmean(float(token["confidence"]) for token in tokens), 6)


def _source(page_number: int, tokens: list[dict[str, Any]], raw_text: str) -> dict[str, Any]:
    return {
        "pdf_page_number": page_number,
        "page_index": page_number - 1,
        "bbox": _bbox(tokens),
        "raw_text": raw_text,
    }


def _ordered_text(tokens: list[dict[str, Any]]) -> str:
    if not tokens:
        return ""
    rows = _group_visual_rows(tokens)
    return " ".join(
        str(token["text"])
        for row in rows
        for token in sorted(row.tokens, key=_token_center_x)
    ).strip()


def _group_visual_rows(tokens: list[dict[str, Any]]) -> list[_VisualRow]:
    if not tokens:
        return []
    median_height = statistics.median(int(token["bbox"]["height"]) for token in tokens)
    tolerance = max(8.0, median_height * 0.65)
    groups: list[list[dict[str, Any]]] = []
    centers: list[float] = []
    for token in sorted(tokens, key=lambda item: (_token_center_y(item), _token_center_x(item))):
        center = _token_center_y(token)
        if not groups or abs(center - centers[-1]) > tolerance:
            groups.append([token])
            centers.append(center)
        else:
            groups[-1].append(token)
            centers[-1] = statistics.fmean(_token_center_y(item) for item in groups[-1])
    return [
        _VisualRow(
            tokens=tuple(sorted(group, key=_token_center_x)),
            center_y=statistics.fmean(_token_center_y(token) for token in group),
        )
        for group in groups
    ]


def _is_year(text: str) -> bool:
    stripped = text.strip()
    return stripped.isdigit() and len(stripped) == 4 and 1900 <= int(stripped) <= 2100


def _is_numericish(text: str) -> bool:
    stripped = text.strip()
    if not stripped or _is_year(stripped):
        return False
    if stripped in {"-", "–", "—"}:
        return True
    return _NUMERICISH_PATTERN.fullmatch(stripped) is not None


def _is_period_day_row(
    visual_rows: list[_VisualRow], row_index: int, value_tokens: list[dict[str, Any]]
) -> bool:
    """Recognize repeated day numbers followed by year headers, such as 31 Aralık."""

    values = [str(token["text"]).strip() for token in value_tokens]
    if len(values) < 2 or not all(value.isdigit() and 1 <= int(value) <= 31 for value in values):
        return False
    current_y = visual_rows[row_index].center_y
    for following in visual_rows[row_index + 1 : row_index + 3]:
        if following.center_y - current_y > 100:
            break
        years = [token for token in following.tokens if _is_year(str(token["text"]))]
        if len(years) >= 2:
            return True
    return False


def _cluster_columns(
    rows: list[dict[str, Any]], page_width: int
) -> list[float]:
    threshold = max(35.0, page_width * 0.05)
    clusters: list[list[tuple[int, float]]] = []
    for row_index, row in enumerate(rows):
        for token in row["value_tokens"]:
            center = _token_center_x(token)
            nearby = [
                (index, abs(center - statistics.median(value for _, value in cluster)))
                for index, cluster in enumerate(clusters)
                if abs(center - statistics.median(value for _, value in cluster)) <= threshold
            ]
            if not nearby:
                clusters.append([(row_index, center)])
            else:
                nearest_index = min(nearby, key=lambda item: item[1])[0]
                clusters[nearest_index].append((row_index, center))
    minimum_support = max(2, math.ceil(len(rows) * 0.6))
    anchors = [
        statistics.median(value for _, value in cluster)
        for cluster in clusters
        if len({row_index for row_index, _ in cluster}) >= minimum_support
    ]
    return sorted(anchors)


def _group_candidate_rows(rows: list[dict[str, Any]], median_height: float) -> list[list[dict[str, Any]]]:
    maximum_gap = max(120.0, median_height * 4.0)
    groups: list[list[dict[str, Any]]] = []
    for row in rows:
        if not groups or row["center_y"] - groups[-1][-1]["center_y"] > maximum_gap:
            groups.append([row])
        else:
            groups[-1].append(row)
    return [group for group in groups if len(group) >= 2]


def _parse_percentage(raw_text: str) -> tuple[Any, str]:
    text = raw_text.strip()
    if not text:
        return None, NumericStatus.BLANK.value
    if text in {"-", "–", "—"}:
        return None, NumericStatus.DASH.value
    match = _PERCENT_PATTERN.fullmatch(text)
    if match:
        value = float(match.group(1).replace(",", "."))
        if 0.0 <= value <= 100.0:
            return value, NumericStatus.PERCENTAGE.value
        return None, NumericStatus.INVALID.value
    range_match = _PERCENT_RANGE_PATTERN.fullmatch(text)
    if range_match:
        minimum = float(range_match.group(1).replace(",", "."))
        maximum = float(range_match.group(2).replace(",", "."))
        if 0.0 <= minimum <= maximum <= 100.0:
            return {
                "min": minimum,
                "max": maximum,
            }, NumericStatus.PERCENTAGE_RANGE.value
        return None, NumericStatus.INVALID.value
    return None, NumericStatus.INVALID.value


def _cell_value(raw_text: str, label: str, column_header: str = "") -> tuple[Any, str]:
    if "%" in label or "%" in raw_text or "%" in column_header:
        return _parse_percentage(raw_text)
    parsed = parse_financial_number(raw_text)
    return parsed.value, parsed.status.value


def _reconcile_unlabeled_totals(rows: list[dict[str, Any]]) -> None:
    """Promote unlabeled rows only when prior rows reconcile in every column."""

    for position, row in enumerate(rows):
        if row.get("label") is not None:
            continue
        prior_total = max(
            (
                index
                for index, previous in enumerate(rows[:position])
                if previous.get("row_type") == "total"
            ),
            default=-1,
        )
        contributors = rows[prior_total + 1 : position]
        if len(contributors) < 2:
            continue
        reconciled = True
        for total_cell in row.get("cells", []):
            column_index = int(total_cell["column_index"])
            if total_cell.get("numeric_status") != NumericStatus.VALUE.value:
                reconciled = False
                break
            values: list[float] = []
            for contributor in contributors:
                cell = next(
                    (
                        item
                        for item in contributor.get("cells", [])
                        if int(item["column_index"]) == column_index
                    ),
                    None,
                )
                if cell is None or cell.get("numeric_status") not in {
                    NumericStatus.VALUE.value,
                    NumericStatus.DASH.value,
                }:
                    reconciled = False
                    break
                values.append(
                    0.0
                    if cell["numeric_status"] == NumericStatus.DASH.value
                    else float(cell["normalized_value"])
                )
            if not reconciled or math.fsum(values) != float(total_cell["normalized_value"]):
                reconciled = False
                break
        if reconciled:
            row["row_type"] = "total"
            row["classification_basis"] = "financial_reconciliation"
            row["aggregation_of_row_ids"] = [
                contributor["row_id"] for contributor in contributors
            ]


def _is_low_confidence_header_noise(token: dict[str, Any]) -> bool:
    """Detect repeated-character OCR artifacts without changing preserved raw text."""

    text = "".join(character for character in str(token["text"]) if character.isalnum())
    return (
        float(token.get("confidence", 0.0)) < 0.5
        and len(text) >= 3
        and len(set(text.casefold())) == 1
    )


def _printed_page_number(tokens: list[dict[str, Any]], page_height: int) -> int | None:
    candidates = []
    for token in tokens:
        text = str(token["text"]).strip()
        if (
            text.isdigit()
            and 0 < int(text) < 1000
            and _token_center_y(token) > page_height * 0.92
        ):
            candidates.append(token)
    if not candidates:
        return None
    page_center = max(_token_right(token) for token in tokens) / 2
    chosen = min(candidates, key=lambda token: abs(_token_center_x(token) - page_center))
    return int(chosen["text"])


def extract_note_page(page: dict[str, Any], note_number: int) -> list[dict[str, Any]]:
    """Extract repeated-column tables without using known note titles, values, or coordinates."""

    page_number = int(page["pdf_page_number"])
    tokens = list(page.get("tokens", []))
    if not tokens:
        raise ValueError(f"note page {page_number} has no OCR tokens")
    page_width = max(_token_right(token) for token in tokens)
    page_height = max(_token_bottom(token) for token in tokens)
    median_height = statistics.median(int(token["bbox"]["height"]) for token in tokens)
    visual_rows = _group_visual_rows(tokens)
    numeric_scan_start = page_width * 0.20
    candidates: list[dict[str, Any]] = []
    for visual_index, row in enumerate(visual_rows):
        value_tokens = [
            token
            for token in row.tokens
            if _token_center_x(token) >= numeric_scan_start
            and _is_numericish(str(token["text"]))
        ]
        if len(value_tokens) >= 2 and not _is_period_day_row(
            visual_rows, visual_index, value_tokens
        ):
            candidates.append(
                {
                    "visual_index": visual_index,
                    "center_y": row.center_y,
                    "tokens": list(row.tokens),
                    "value_tokens": value_tokens,
                }
            )
    groups = _group_candidate_rows(candidates, median_height)
    tables: list[dict[str, Any]] = []
    used_orphan_rows: set[int] = set()
    for group in groups:
        anchors = _cluster_columns(group, page_width)
        if len(anchors) < 2:
            continue
        table_numeric_start = max(page_width * 0.10, anchors[0] - page_width * 0.08)
        first_y = float(group[0]["center_y"])
        header_window = max(260.0, median_height * 10.0)
        label_boundary = anchors[0] - page_width * 0.045
        first_visual_index = int(group[0]["visual_index"])
        first_orphan_indices = {
            index
            for index, row in enumerate(visual_rows)
            if index < first_visual_index
            and first_y - row.center_y <= median_height * 2.3
            and row.tokens
            and max(_token_right(token) for token in row.tokens) < label_boundary
        }
        header_rows = [
            row
            for index, row in enumerate(visual_rows)
            if index not in first_orphan_indices
            and first_y - header_window <= row.center_y
            < first_y - median_height * 0.55
            and any(_token_center_x(token) >= table_numeric_start for token in row.tokens)
        ]
        connected_header_rows: list[_VisualRow] = []
        maximum_header_gap = max(70.0, median_height * 1.8)
        for row in reversed(header_rows):
            if (
                connected_header_rows
                and connected_header_rows[-1].center_y - row.center_y > maximum_header_gap
            ):
                break
            connected_header_rows.append(row)
        connected_header_rows.reverse()
        header_tokens = [
            token
            for row in connected_header_rows
            for token in row.tokens
            if _token_center_x(token) >= table_numeric_start
        ]
        table_id = f"note-{note_number}-p{page_number}-t{len(tables) + 1}"
        table_warnings: list[dict[str, Any]] = []
        column_headers: list[dict[str, Any]] = []
        header_warning = False
        for column_index, anchor in enumerate(anchors, start=1):
            if len(anchors) == 1:
                left_bound, right_bound = 0.0, float(page_width)
            else:
                left_bound = (
                    table_numeric_start
                    if column_index == 1
                    else (anchors[column_index - 2] + anchor) / 2
                )
                right_bound = (
                    float(page_width)
                    if column_index == len(anchors)
                    else (anchor + anchors[column_index]) / 2
                )
            assigned_header = [
                token
                for token in header_tokens
                if left_bound <= _token_center_x(token) < right_bound
            ]
            raw_header = _ordered_text(assigned_header)
            if not raw_header:
                header_warning = True
                raw_header = f"column_{column_index}"
            normalized_header_tokens = [
                token
                for token in assigned_header
                if not _is_low_confidence_header_noise(token)
            ]
            normalized_header = _ordered_text(normalized_header_tokens) or raw_header
            column_id = f"{table_id}:column-{column_index}"
            if normalized_header != raw_header:
                table_warnings.append(
                    {
                        "code": "column_header_ocr_noise_removed",
                        "column_id": column_id,
                        "raw_text": raw_header,
                        "normalized_text": normalized_header,
                    }
                )
            column_headers.append(
                {
                    "column_id": column_id,
                    "column_index": column_index,
                    "role": "column_header",
                    "raw_text": raw_header,
                    "normalized_text": normalized_header,
                    "bbox": _bbox(assigned_header),
                    "confidence": _confidence(assigned_header),
                    "source": _source(page_number, assigned_header, raw_header),
                    "anchor_x": round(anchor, 2),
                }
            )
        if header_warning:
            table_warnings.append({"code": "missing_column_header"})
        rows: list[dict[str, Any]] = []
        previous_data_y = first_y - header_window
        for row_index, candidate in enumerate(group, start=1):
            current_tokens = list(candidate["tokens"])
            label_tokens = [
                token for token in current_tokens if _token_center_x(token) < label_boundary
            ]
            orphan_candidates = [
                (index, row)
                for index, row in enumerate(visual_rows)
                if index not in used_orphan_rows
                and previous_data_y < row.center_y < candidate["center_y"]
                and candidate["center_y"] - row.center_y <= median_height * 2.3
                and row.tokens
                and max(_token_right(token) for token in row.tokens) < label_boundary
            ]
            if orphan_candidates:
                orphan_index, orphan = max(orphan_candidates, key=lambda item: item[1].center_y)
                label_tokens = list(orphan.tokens) + label_tokens
                used_orphan_rows.add(orphan_index)
            label = _ordered_text(label_tokens)
            if not label:
                table_warnings.append(
                    {"code": "missing_row_label", "row_index": row_index}
                )
            assigned_by_column: dict[int, dict[str, Any]] = {}
            extras: list[str] = []
            maximum_distance = page_width * 0.09
            for token in candidate["value_tokens"]:
                nearest = min(range(len(anchors)), key=lambda index: abs(_token_center_x(token) - anchors[index]))
                distance = abs(_token_center_x(token) - anchors[nearest])
                if distance > maximum_distance:
                    extras.append(str(token["text"]))
                    continue
                current = assigned_by_column.get(nearest)
                if current is None or distance < current["distance"]:
                    if current is not None:
                        extras.append(str(current["token"]["text"]))
                    assigned_by_column[nearest] = {"token": token, "distance": distance}
                else:
                    extras.append(str(token["text"]))
            if extras:
                table_warnings.append(
                    {
                        "code": "extra_numeric_token",
                        "row_index": row_index,
                        "raw_text": " ".join(extras),
                    }
                )
            cells: list[dict[str, Any]] = []
            valid_cells = 0
            present_cells = 0
            for column_index, header in enumerate(column_headers):
                assignment = assigned_by_column.get(column_index)
                cell_tokens = [assignment["token"]] if assignment else []
                raw_text = _ordered_text(cell_tokens)
                normalized_value, numeric_status = _cell_value(
                    raw_text, label, header["normalized_text"]
                )
                if cell_tokens:
                    present_cells += 1
                if numeric_status != NumericStatus.INVALID.value:
                    valid_cells += 1
                if not cell_tokens:
                    table_warnings.append(
                        {
                            "code": "missing_data_cell",
                            "row_index": row_index,
                            "column_index": column_index + 1,
                        }
                    )
                elif numeric_status == NumericStatus.INVALID.value:
                    table_warnings.append(
                        {
                            "code": "invalid_note_value",
                            "row_index": row_index,
                            "column_index": column_index + 1,
                            "raw_text": raw_text,
                        }
                    )
                cells.append(
                    {
                        "role": "data_cell",
                        "column_id": header["column_id"],
                        "column_index": column_index + 1,
                        "column_header": header["normalized_text"],
                        "column_header_raw": header["raw_text"],
                        "raw_text": raw_text,
                        "normalized_value": normalized_value,
                        "numeric_status": numeric_status,
                        "bbox": _bbox(cell_tokens),
                        "confidence": _confidence(cell_tokens),
                        "source": _source(page_number, cell_tokens, raw_text),
                    }
                )
            completeness = present_cells / len(anchors)
            validity = valid_cells / len(anchors)
            evidence_tokens = label_tokens + [
                item["token"] for item in assigned_by_column.values()
            ]
            evidence_confidence = _confidence(evidence_tokens)
            row_confidence = round(
                0.6 * evidence_confidence + 0.2 * completeness + 0.2 * validity,
                6,
            )
            lowered_label = label.casefold()
            row_type = (
                "total"
                if "toplam" in lowered_label
                or "kapanış bakiyesi" in lowered_label
                or "net defter değeri" in lowered_label
                else "unresolved"
                if not label
                else "detail"
            )
            classification_basis = (
                "explicit_label"
                if row_type == "total"
                else "missing_label"
                if row_type == "unresolved"
                else "detail_label"
            )
            row_tokens = label_tokens + [
                item["token"] for item in assigned_by_column.values()
            ]
            rows.append(
                {
                    "row_id": f"{table_id}:row-{row_index}",
                    "row_index": row_index,
                    "row_type": row_type,
                    "classification_basis": classification_basis,
                    "aggregation_of_row_ids": [],
                    "label": label or None,
                    "cells": cells,
                    "bbox": _bbox(row_tokens),
                    "confidence": row_confidence,
                    "source": _source(page_number, row_tokens, label),
                }
            )
            previous_data_y = float(candidate["center_y"])
        _reconcile_unlabeled_totals(rows)
        row_label_rate = sum(row["label"] is not None for row in rows) / len(rows)
        cell_assignment_rate = sum(
            cell["bbox"] is not None for row in rows for cell in row["cells"]
        ) / (len(rows) * len(anchors))
        value_parse_rate = sum(
            cell["numeric_status"] != NumericStatus.INVALID.value
            for row in rows
            for cell in row["cells"]
        ) / (len(rows) * len(anchors))
        header_confidence = statistics.fmean(
            header["confidence"] for header in column_headers
        )
        mean_row_confidence = statistics.fmean(row["confidence"] for row in rows)
        table_confidence = round(
            statistics.fmean(
                [
                    header_confidence,
                    row_label_rate,
                    cell_assignment_rate,
                    value_parse_rate,
                    mean_row_confidence,
                ]
            ),
            6,
        )
        table_tokens = header_tokens + [
            token
            for candidate in group
            for token in candidate["tokens"]
        ]
        tables.append(
            {
                "table_id": table_id,
                "table_type": "disclosure_note_table",
                "note_number": note_number,
                "page": {
                    "pdf_page_number": page_number,
                    "page_index": page_number - 1,
                    "printed_page_number": _printed_page_number(tokens, page_height),
                },
                "bbox": _bbox(table_tokens),
                "columns": column_headers,
                "rows": rows,
                "quality": {
                    "row_label_assignment_rate": round(row_label_rate, 6),
                    "data_cell_assignment_rate": round(cell_assignment_rate, 6),
                    "value_parse_success_rate": round(value_parse_rate, 6),
                },
                "confidence": table_confidence,
                "warnings": table_warnings,
            }
        )
    return tables


def extract_note_document(
    ocr_output: dict[str, Any], locations: list[dict[str, Any]]
) -> dict[str, Any]:
    """Extract every detected table from all pages assigned to each target note."""

    pages_by_number = {
        int(page["pdf_page_number"]): page for page in ocr_output.get("pages", [])
    }
    notes: list[dict[str, Any]] = []
    for location in locations:
        note_number = int(location["note_number"])
        page_numbers = [int(page) for page in location["pdf_pages"]]
        missing = [page for page in page_numbers if page not in pages_by_number]
        if missing:
            raise ValueError(
                f"note OCR artifact is missing located pages for note {note_number}: {missing}"
            )
        tables = [
            table
            for page_number in page_numbers
            for table in extract_note_page(pages_by_number[page_number], note_number)
        ]
        if not tables:
            raise ValueError(f"no tables were extracted for configured note {note_number}")
        notes.append(
            {
                "note_number": note_number,
                "title": location.get("title"),
                "pdf_pages": page_numbers,
                "location_confidence": float(location["confidence"]),
                "tables": tables,
            }
        )
    has_warnings = any(
        table["warnings"] for note in notes for table in note["tables"]
    )
    return {
        "stage": "note_extraction",
        "status": "completed_with_warnings" if has_warnings else "completed",
        "notes": notes,
    }