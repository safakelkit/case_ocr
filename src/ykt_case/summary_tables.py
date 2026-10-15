# Bu dosya, özet finansal tabloları OCR koordinatlarından satır, hücre ve hiyerarşi yapısıyla çıkarmak için kullanılır.
"""Geometry-based reconstruction of summary financial tables from OCR tokens."""

from __future__ import annotations

from dataclasses import dataclass
import re
import statistics
from typing import Any

from ykt_case.normalization import NumericStatus, parse_financial_number


_YEAR_PATTERN = re.compile(r"^(?:19|20)\d{2}$")
_OCR_REPAIR_CONFIDENCE_CEILING = 0.9


@dataclass(frozen=True)
class _Line:
    tokens: tuple[dict[str, Any], ...]
    text: str
    left: int
    top: int
    right: int
    bottom: int

    @property
    def center_y(self) -> float:
        return (self.top + self.bottom) / 2

    @property
    def confidence(self) -> float:
        return statistics.fmean(float(token["confidence"]) for token in self.tokens)


def _token_right(token: dict[str, Any]) -> int:
    return int(token["bbox"]["left"]) + int(token["bbox"]["width"])


def _token_bottom(token: dict[str, Any]) -> int:
    return int(token["bbox"]["top"]) + int(token["bbox"]["height"])


def _token_center_x(token: dict[str, Any]) -> float:
    return int(token["bbox"]["left"]) + int(token["bbox"]["width"]) / 2


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


def _group_lines(tokens: list[dict[str, Any]]) -> list[_Line]:
    groups: dict[tuple[int, int, int], list[dict[str, Any]]] = {}
    for token in tokens:
        key = (
            int(token["block_number"]),
            int(token["paragraph_number"]),
            int(token["line_number"]),
        )
        groups.setdefault(key, []).append(token)

    lines: list[_Line] = []
    for group in groups.values():
        ordered = tuple(sorted(group, key=lambda token: int(token["bbox"]["left"])))
        lines.append(
            _Line(
                tokens=ordered,
                text=" ".join(str(token["text"]) for token in ordered),
                left=min(int(token["bbox"]["left"]) for token in ordered),
                top=min(int(token["bbox"]["top"]) for token in ordered),
                right=max(_token_right(token) for token in ordered),
                bottom=max(_token_bottom(token) for token in ordered),
            )
        )
    return sorted(lines, key=lambda line: (line.top, line.left))


def _is_uppercase_label(text: str) -> bool:
    letters = [character for character in text if character.isalpha()]
    return bool(letters) and all(character.isupper() for character in letters)


def _find_period_header(lines: list[_Line]) -> tuple[_Line, list[dict[str, Any]]]:
    candidates: list[tuple[_Line, list[dict[str, Any]]]] = []
    for line in lines:
        years = [token for token in line.tokens if _YEAR_PATTERN.fullmatch(str(token["text"]))]
        if len(years) >= 2:
            candidates.append((line, sorted(years, key=_token_center_x)))
    if not candidates:
        raise ValueError("expected at least two period headers on the summary page")
    return max(candidates, key=lambda item: item[0].top)


def _find_note_anchor(
    lines: list[_Line], header: _Line
) -> tuple[float, list[dict[str, Any]]]:
    candidates: list[dict[str, Any]] = []
    for line in lines:
        if abs(line.center_y - header.center_y) > 120:
            continue
        for token in line.tokens:
            folded = str(token["text"]).casefold()
            if "referans" in folded or folded == "dipnot":
                candidates.append(token)
    if candidates:
        return (
            statistics.fmean(_token_center_x(token) for token in candidates),
            candidates,
        )
    raise ValueError("note-reference column header was not found on the summary page")


def _find_printed_page_number(lines: list[_Line], after_y: float) -> int | None:
    candidates: list[tuple[int, int]] = []
    for line in lines:
        if line.center_y <= after_y or len(line.tokens) != 1:
            continue
        text = str(line.tokens[0]["text"])
        if text.isdigit() and 0 < int(text) < 1000:
            candidates.append((line.top, int(text)))
    return max(candidates)[1] if candidates else None


def _source(page_number: int, bbox: dict[str, int] | None, raw_text: str) -> dict[str, Any]:
    return {
        "pdf_page_number": page_number,
        "page_index": page_number - 1,
        "bbox": bbox,
        "raw_text": raw_text,
    }


def _line_cell(line: _Line, role: str, page_number: int) -> dict[str, Any]:
    return {
        "role": role,
        "raw_text": line.text,
        "bbox": _bbox(line.tokens),
        "confidence": round(line.confidence, 6),
        "source": _source(page_number, _bbox(line.tokens), line.text),
    }


def _period_values(
    row: dict[str, Any], *, dash_as_zero: bool = False
) -> dict[str, int | float] | None:
    values: dict[str, int | float] = {}
    for cell in row.get("cells", []):
        if cell.get("role") != "data_cell":
            continue
        period = cell.get("period")
        value = cell.get("normalized_value")
        status = cell.get("numeric_status")
        if dash_as_zero and status == NumericStatus.DASH.value:
            values[str(period)] = 0
            continue
        if status != NumericStatus.VALUE.value or value is None:
            return None
        values[str(period)] = value
    return values or None


def _values_match(
    left: dict[str, int | float], right: dict[str, int | float]
) -> bool:
    return set(left) == set(right) and all(
        abs(float(left[period]) - float(right[period])) <= 1e-6
        for period in left
    )


def _rows_reconcile(
    target_row: dict[str, Any], candidate_rows: list[dict[str, Any]]
) -> bool:
    target = _period_values(target_row, dash_as_zero=True)
    if target is None or not candidate_rows:
        return False
    candidate_values = [
        _period_values(row, dash_as_zero=True) for row in candidate_rows
    ]
    if any(values is None or set(values) != set(target) for values in candidate_values):
        return False
    sums = {
        period: sum(float(values[period]) for values in candidate_values if values)
        for period in target
    }
    return _values_match(target, sums)


def _separator_alternative(raw_text: str, label: str | None) -> int | None:
    """Return a possible integer when OCR may have swapped '.' for ','."""

    if label and "hisse başına" in label.casefold():
        return None
    text = raw_text.strip()
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1].strip()
    if re.fullmatch(r"(?:0|[1-9]\d{0,2}(?:\.\d{3})*|[1-9]\d*),\d{3}", text) is None:
        return None
    alternative = int(text.replace(".", "").replace(",", ""))
    return -alternative if negative else alternative


def _resolve_child_separator_ambiguities(
    parent: dict[str, Any], children: list[dict[str, Any]]
) -> None:
    """Resolve one separator ambiguity only when it uniquely restores a parent sum."""

    target = _period_values(parent, dash_as_zero=True)
    if target is None:
        return
    for period, target_value in target.items():
        target_cell = next(
            (
                item
                for item in parent.get("cells", [])
                if item.get("role") == "data_cell"
                and str(item.get("period")) == period
            ),
            None,
        )
        if target_cell is None or (
            float(target_cell.get("confidence", 1.0))
            < _OCR_REPAIR_CONFIDENCE_CEILING
        ):
            continue
        cells: list[dict[str, Any]] = []
        for child in children:
            cell = next(
                (
                    item
                    for item in child.get("cells", [])
                    if item.get("role") == "data_cell"
                    and str(item.get("period")) == period
                ),
                None,
            )
            if cell is None or cell.get("numeric_status") not in {
                NumericStatus.VALUE.value,
                NumericStatus.DASH.value,
            }:
                cells = []
                break
            cells.append(cell)
        if not cells:
            continue
        primary_sum = sum(
            0.0
            if cell.get("numeric_status") == NumericStatus.DASH.value
            else float(cell["normalized_value"])
            for cell in cells
        )
        solutions: list[tuple[dict[str, Any], int | float]] = []
        for cell in cells:
            candidates = cell.get("normalization_candidates", [])
            if len(candidates) < 2:
                continue
            primary = float(cell["normalized_value"])
            for candidate in candidates:
                if abs(float(candidate) - primary) <= 1e-9:
                    continue
                if abs(primary_sum - primary + float(candidate) - float(target_value)) <= 1e-6:
                    solutions.append((cell, candidate))
        if len(solutions) != 1:
            continue
        cell, selected = solutions[0]
        original = cell["normalized_value"]
        cell["parser_normalized_value"] = original
        cell["normalized_value"] = selected
        cell["normalization_resolution"] = {
            "method": "parent_child_financial_reconciliation",
            "parser_normalized_value": original,
            "selected_normalized_value": selected,
            "target_row_id": parent["row_id"],
            "period": period,
            "target_confidence": target_cell.get("confidence"),
        }


def _digit_edit_distance(left: int | float, right: int | float) -> int | None:
    if not float(left).is_integer() or not float(right).is_integer():
        return None
    left_text = str(abs(int(left)))
    right_text = str(abs(int(right)))
    if len(left_text) != len(right_text):
        return None
    return sum(a != b for a, b in zip(left_text, right_text))


def _resolve_child_digit_ambiguities(
    parent: dict[str, Any], children: list[dict[str, Any]]
) -> None:
    """Repair one low-confidence digit only when the parent residual proves it."""

    target = _period_values(parent, dash_as_zero=True)
    if target is None:
        return
    for period, target_value in target.items():
        target_cell = next(
            (
                cell
                for cell in parent.get("cells", [])
                if cell.get("role") == "data_cell"
                and str(cell.get("period")) == period
            ),
            None,
        )
        if target_cell is None or (
            float(target_cell.get("confidence", 1.0))
            < _OCR_REPAIR_CONFIDENCE_CEILING
        ):
            continue
        cells = [
            next(
                (
                    cell
                    for cell in child.get("cells", [])
                    if cell.get("role") == "data_cell"
                    and str(cell.get("period")) == period
                ),
                None,
            )
            for child in children
        ]
        if any(cell is None for cell in cells):
            continue
        usable = [
            cell
            for cell in cells
            if cell is not None
            and cell.get("numeric_status") in {
                NumericStatus.VALUE.value,
                NumericStatus.DASH.value,
            }
        ]
        if len(usable) != len(cells):
            continue
        primary_sum = sum(
            0.0
            if cell.get("numeric_status") == NumericStatus.DASH.value
            else float(cell["normalized_value"])
            for cell in usable
        )
        if abs(primary_sum - float(target_value)) <= 1e-6:
            continue
        candidates: list[tuple[dict[str, Any], int]] = []
        for cell in usable:
            if cell.get("numeric_status") != NumericStatus.VALUE.value:
                continue
            current = cell.get("normalized_value")
            if not isinstance(current, (int, float)):
                continue
            required = float(target_value) - (primary_sum - float(current))
            if not required.is_integer():
                continue
            required_integer = int(required)
            if _digit_edit_distance(current, required_integer) != 1:
                continue
            if float(cell.get("confidence", 1.0)) >= _OCR_REPAIR_CONFIDENCE_CEILING:
                continue
            candidates.append((cell, required_integer))
        if len(candidates) != 1:
            continue
        cell, selected = candidates[0]
        original = cell["normalized_value"]
        cell["parser_normalized_value"] = original
        cell["normalization_ambiguity"] = "single_digit_ocr_error"
        cell["normalization_candidates"] = [original, selected]
        cell["normalized_value"] = selected
        cell["normalization_resolution"] = {
            "method": "parent_child_residual_single_digit_reconciliation",
            "parser_normalized_value": original,
            "selected_normalized_value": selected,
            "target_row_id": parent["row_id"],
            "period": period,
            "ocr_confidence": cell.get("confidence"),
            "confidence_ceiling": _OCR_REPAIR_CONFIDENCE_CEILING,
            "target_confidence": target_cell.get("confidence"),
        }


def _reconciled_preceding_rows(
    rows: list[dict[str, Any]], total_index: int
) -> list[str]:
    """Return the shortest exact contiguous suffix explaining a subtotal/total."""

    target = _period_values(rows[total_index], dash_as_zero=True)
    if target is None:
        return []
    candidates: list[dict[str, Any]] = []
    for index in range(total_index - 1, -1, -1):
        candidate = rows[index]
        if candidate.get("row_type") == "section_header":
            break
        values = _period_values(candidate, dash_as_zero=True)
        if values is None or set(values) != set(target):
            continue
        candidates.insert(0, candidate)
        if _rows_reconcile(rows[total_index], candidates):
            return [str(item["row_id"]) for item in candidates]
    return []


def _set_aggregation(
    row: dict[str, Any],
    candidate_rows: list[dict[str, Any]],
    basis: str,
) -> None:
    row["aggregation_of_row_ids"] = [str(item["row_id"]) for item in candidate_rows]
    row["aggregation_status"] = "reconciled"
    row["aggregation_basis"] = basis
    for candidate in candidate_rows:
        candidate.setdefault("aggregated_by_row_ids", []).append(row["row_id"])


def _is_non_additive_row(row: dict[str, Any]) -> bool:
    label = str(row.get("label") or "").casefold()
    return "hisse başına" in label


def _presentation_section_indexes(rows: list[dict[str, Any]]) -> set[int]:
    """Identify distribution blocks that restate, rather than add to, a prior total."""

    excluded: set[int] = set()
    for start, row in enumerate(rows):
        if row.get("row_type") != "section_header":
            continue
        for end in range(start + 1, len(rows)):
            candidate = rows[end]
            if candidate.get("row_type") == "section_header":
                break
            if candidate.get("label") is None and candidate.get("aggregation_status") == "reconciled":
                excluded.update(range(start, end + 1))
                break
    return excluded


def _preceding_frontier(
    rows: list[dict[str, Any]], total_index: int
) -> list[dict[str, Any]]:
    target = rows[total_index]
    target_level = int(target.get("hierarchy_level", 0))
    excluded_indexes = _presentation_section_indexes(rows)
    candidates = [
        row
        for index, row in enumerate(rows[:total_index])
        if index not in excluded_indexes
        and row.get("row_type") != "section_header"
        and int(row.get("hierarchy_level", 0)) == target_level
        and not _is_non_additive_row(row)
    ]
    candidate_ids = {str(row["row_id"]) for row in candidates}
    candidates = [
        row
        for row in candidates
        if not any(
            aggregator in candidate_ids
            for aggregator in row.get("aggregated_by_row_ids", [])
        )
    ]
    suffix: list[dict[str, Any]] = []
    for candidate in reversed(candidates):
        suffix.insert(0, candidate)
        if _rows_reconcile(target, suffix):
            return suffix
    return []


def _assign_row_relationships(table_id: str, rows: list[dict[str, Any]]) -> None:
    """Attach conservative geometry-based hierarchy and verified aggregation links."""

    indentation_threshold = 18
    for index, row in enumerate(rows, start=1):
        row["extracted_row_type"] = row["row_type"]
        row["row_id"] = f"{table_id}:row-{index}"
        row["parent_row_id"] = None
        row["child_row_ids"] = []
        row["hierarchy_level"] = 0
        row["hierarchy_basis"] = "none"
        row["hierarchy_confidence"] = 0.0

    # Promote an unlabeled financial line to a total only when the immediately
    # preceding rows reconcile exactly for every period. Missing text alone is
    # never sufficient evidence for a total classification.
    for index, row in enumerate(rows):
        if row.get("label") is not None or row.get("row_type") != "detail":
            continue
        if _reconciled_preceding_rows(rows, index):
            row["row_type"] = "total"

    current_section: dict[str, Any] | None = None
    parent_stack: list[dict[str, Any]] = []
    by_id = {str(row["row_id"]): row for row in rows}
    for row in rows:
        if row["row_type"] == "section_header":
            current_section = row
            parent_stack = []
            row["hierarchy_basis"] = "explicit_section_header"
            row["hierarchy_confidence"] = 1.0
            continue

        if not row.get("label"):
            # An unlabeled financial line is an explicit boundary of uncertainty.
            # A reconciled total stays parentless and records aggregation evidence
            # later; any other unlabeled line remains unresolved rather than being
            # attached to the preceding detail row by indentation.
            current_section = None
            parent_stack = []
            row["hierarchy_basis"] = (
                "financial_reconciliation"
                if row["row_type"] == "total"
                else "unlabeled_boundary"
            )
            row["hierarchy_confidence"] = (
                1.0 if row["row_type"] == "total" else 0.0
            )
            continue

        left = int((row.get("bbox") or {}).get("left", 0))
        parent_stack = [
            candidate
            for candidate in parent_stack
            if int((candidate.get("bbox") or {}).get("left", 0))
            < left - indentation_threshold
        ]
        parent = parent_stack[-1] if parent_stack else current_section
        if parent is not None:
            row["parent_row_id"] = parent["row_id"]
            parent["child_row_ids"].append(row["row_id"])
            row["hierarchy_level"] = int(parent["hierarchy_level"]) + 1
            row["hierarchy_basis"] = (
                "indentation"
                if parent["row_type"] != "section_header"
                else "section_membership"
            )
            row["hierarchy_confidence"] = (
                0.9 if parent["row_type"] != "section_header" else 0.7
            )

        # Only detail rows act as indentation-derived parents. Subtotals and totals
        # are calculation outputs unless exact aggregation evidence is available.
        if row["row_type"] == "detail" and row.get("label"):
            parent_stack.append(row)

    for row in rows:
        row["aggregation_of_row_ids"] = []
        row["aggregation_status"] = (
            "unresolved" if row["row_type"] in {"subtotal", "total"} else "not_applicable"
        )
        row["aggregation_basis"] = (
            "no_exact_non_overlapping_reconciliation"
            if row["aggregation_status"] == "unresolved"
            else "not_applicable"
        )
        row["aggregated_by_row_ids"] = []

    # Unlabeled distribution totals are intentionally parentless, so preserve
    # their exact contiguous reconciliation before using hierarchy frontiers.
    for index, row in enumerate(rows):
        if row.get("label") is not None or row.get("row_type") != "total":
            continue
        candidate_ids = _reconciled_preceding_rows(rows, index)
        candidates = [by_id[candidate_id] for candidate_id in candidate_ids]
        if candidates:
            _set_aggregation(row, candidates, "contiguous_unlabeled_total")

    # Geometry-derived parents provide the safest subtotal boundary. A possible
    # decimal/thousands OCR swap is resolved only if one alternative uniquely
    # restores the exact parent sum in the affected period.
    for row in rows:
        children = [by_id[child_id] for child_id in row.get("child_row_ids", [])]
        if not children:
            continue
        _resolve_child_separator_ambiguities(row, children)
        _resolve_child_digit_ambiguities(row, children)
        if _rows_reconcile(row, children):
            if row["row_type"] == "detail":
                row["row_type"] = "subtotal"
            _set_aggregation(row, children, "direct_hierarchy_children")

    # Some financial statements print a subtotal before its following
    # components. Reconcile the same-level frontier until the next explicit
    # subtotal/total/section boundary.
    for index, row in enumerate(rows):
        if row.get("aggregation_status") == "reconciled" or row.get("row_type") == "section_header":
            continue
        following: list[dict[str, Any]] = []
        for candidate in rows[index + 1 :]:
            if candidate.get("extracted_row_type") in {
                "subtotal",
                "total",
                "section_header",
            }:
                break
            if int(candidate.get("hierarchy_level", 0)) == int(row.get("hierarchy_level", 0)):
                following.append(candidate)
        if following and _rows_reconcile(row, following):
            if row["row_type"] == "detail":
                row["row_type"] = "subtotal"
            _set_aggregation(row, following, "following_same_level_components")

    # Remaining explicit totals are checked against a non-overlapping preceding
    # frontier. Components already represented by a reconciled parent are
    # excluded, preventing parent-plus-child double counting.
    for index, row in enumerate(rows):
        if row["row_type"] not in {"subtotal", "total"}:
            continue
        if row.get("aggregation_status") == "reconciled":
            continue
        candidates = _preceding_frontier(rows, index)
        if candidates:
            _set_aggregation(row, candidates, "preceding_non_overlapping_frontier")

    for row in rows:
        if row["row_type"] == "section_header":
            row["hierarchy_role"] = "section"
        elif row["row_type"] in {"subtotal", "total"}:
            row["hierarchy_role"] = row["row_type"]
        elif row["child_row_ids"]:
            row["hierarchy_role"] = "parent"
        else:
            row["hierarchy_role"] = "leaf"


def extract_summary_page(page: dict[str, Any]) -> dict[str, Any]:
    """Reconstruct one summary table using detected headers and token geometry."""

    page_number = int(page["pdf_page_number"])
    tokens = list(page["tokens"])
    if not tokens:
        raise ValueError(f"summary page {page_number} has no OCR tokens")
    lines = _group_lines(tokens)
    header_line, year_tokens = _find_period_header(lines)
    periods = [str(token["text"]) for token in year_tokens]
    period_x = [_token_center_x(token) for token in year_tokens]
    period_gap = statistics.median(
        right - left for left, right in zip(period_x, period_x[1:])
    )
    note_x, note_header_tokens = _find_note_anchor(lines, header_line)
    label_cutoff = (note_x + period_x[0]) / 2
    maximum_period_distance = max(80.0, period_gap * 0.45)

    data_rows: list[dict[str, Any]] = []
    for line in lines:
        if line.center_y <= header_line.bottom:
            continue
        assigned: dict[int, list[dict[str, Any]]] = {index: [] for index in range(len(periods))}
        unassigned_numeric: list[dict[str, Any]] = []
        for token in line.tokens:
            parsed = parse_financial_number(str(token["text"]))
            if parsed.status not in {NumericStatus.VALUE, NumericStatus.DASH}:
                continue
            center_x = _token_center_x(token)
            nearest = min(range(len(period_x)), key=lambda index: abs(center_x - period_x[index]))
            if abs(center_x - period_x[nearest]) <= maximum_period_distance:
                assigned[nearest].append(token)
            else:
                unassigned_numeric.append(token)
        if not any(assigned.values()):
            continue

        note_tokens = [
            token
            for token in unassigned_numeric
            if note_x - period_gap * 0.5
            <= _token_center_x(token)
            < (note_x + period_x[0]) / 2
            and abs(_token_center_x(token) - note_x) <= period_gap * 0.5
        ]
        value_tokens = [token for group in assigned.values() for token in group]
        data_rows.append(
            {
                "line": line,
                "center_y": statistics.fmean(
                    int(token["bbox"]["top"]) + int(token["bbox"]["height"]) / 2
                    for token in value_tokens
                ),
                "assigned": assigned,
                "note_tokens": note_tokens,
            }
        )

    if not data_rows:
        raise ValueError(f"no financial rows found on summary page {page_number}")

    last_data_y = max(row["center_y"] for row in data_rows)
    label_lines = [
        line
        for line in lines
        if header_line.bottom < line.center_y <= last_data_y + 80
        and line.right < label_cutoff
        and not all(str(token["text"]).isdigit() for token in line.tokens)
    ]
    median_height = statistics.median(line.bottom - line.top for line in label_lines)
    row_tolerance = max(45.0, median_height * 2.2)
    direct_match_tolerance = max(30.0, median_height * 1.25)
    primary_label_by_row: dict[int, tuple[int, _Line]] = {}
    for label_index, label_line in enumerate(label_lines):
        nearest_row_index = min(
            range(len(data_rows)),
            key=lambda index: abs(data_rows[index]["center_y"] - label_line.center_y),
        )
        distance = abs(data_rows[nearest_row_index]["center_y"] - label_line.center_y)
        if distance > direct_match_tolerance:
            continue
        current = primary_label_by_row.get(nearest_row_index)
        if current is None or distance < abs(
            data_rows[nearest_row_index]["center_y"] - current[1].center_y
        ):
            primary_label_by_row[nearest_row_index] = (label_index, label_line)
    used_labels: set[int] = set()
    reconstructed: list[tuple[float, dict[str, Any]]] = []
    warnings: list[dict[str, Any]] = []

    for data_row_index, data in enumerate(data_rows):
        available = [
            (index, line)
            for index, line in enumerate(label_lines)
            if index not in used_labels and abs(line.center_y - data["center_y"]) <= row_tolerance
        ]
        label_group: list[tuple[int, _Line]] = []
        primary = primary_label_by_row.get(data_row_index)
        if primary is not None and primary[0] not in used_labels:
            nearest_index, nearest_line = primary
            label_group.append((nearest_index, nearest_line))
            preceding = [item for item in available if item[1].center_y < nearest_line.center_y]
            if preceding:
                previous_index, previous_line = max(preceding, key=lambda item: item[1].center_y)
                if (
                    nearest_line.center_y - previous_line.center_y <= median_height * 2.0
                    and nearest_line.left >= previous_line.left + 8
                ):
                    label_group.insert(0, (previous_index, previous_line))
            used_labels.update(index for index, _ in label_group)

        label_tokens = [token for _, line in label_group for token in line.tokens]
        label_text = " ".join(line.text for _, line in label_group)
        if not label_text:
            warnings.append(
                {
                    "code": "missing_row_label",
                    "financial_row_index": data_row_index + 1,
                    "source_y": round(data["center_y"], 1),
                }
            )
        cells: list[dict[str, Any]] = []
        if label_tokens:
            cells.append(
                {
                    "role": "row_header",
                    "raw_text": label_text,
                    "bbox": _bbox(label_tokens),
                    "confidence": _confidence(label_tokens),
                    "source": _source(page_number, _bbox(label_tokens), label_text),
                }
            )
        note_tokens = data["note_tokens"]
        note_reference = " ".join(str(token["text"]) for token in note_tokens) or None
        if note_tokens:
            cells.append(
                {
                    "role": "note_reference",
                    "raw_text": note_reference,
                    "bbox": _bbox(note_tokens),
                    "confidence": _confidence(note_tokens),
                    "source": _source(page_number, _bbox(note_tokens), note_reference),
                }
            )

        present_periods = 0
        for period_index, period in enumerate(periods):
            cell_tokens = data["assigned"][period_index]
            raw_text = " ".join(str(token["text"]) for token in cell_tokens)
            parsed = parse_financial_number(raw_text)
            if cell_tokens:
                present_periods += 1
            cell = {
                "role": "data_cell",
                "period": period,
                "raw_text": raw_text,
                "normalized_value": parsed.value,
                "numeric_status": parsed.status.value,
                "bbox": _bbox(cell_tokens),
                "confidence": _confidence(cell_tokens),
                "source": _source(page_number, _bbox(cell_tokens), raw_text),
            }
            separator_alternative = _separator_alternative(raw_text, label_text or None)
            if (
                parsed.status is NumericStatus.VALUE
                and separator_alternative is not None
                and separator_alternative != parsed.value
            ):
                cell["normalization_ambiguity"] = "decimal_or_thousands_separator"
                cell["normalization_candidates"] = [
                    parsed.value,
                    separator_alternative,
                ]
                warnings.append(
                    {
                        "code": "ambiguous_decimal_or_thousands_separator",
                        "financial_row_index": data_row_index + 1,
                        "period": period,
                        "raw_text": raw_text,
                        "candidates": [parsed.value, separator_alternative],
                    }
                )
            cells.append(cell)
            if parsed.status is NumericStatus.INVALID:
                warnings.append(
                    {
                        "code": "invalid_financial_value",
                        "financial_row_index": data_row_index + 1,
                        "period": period,
                        "raw_text": raw_text,
                    }
                )

        if label_text.casefold().startswith("toplam"):
            row_type = "total"
        elif label_text and _is_uppercase_label(label_text):
            row_type = "subtotal"
        else:
            row_type = "detail"
        evidence_confidences = [cell["confidence"] for cell in cells if cell["bbox"] is not None]
        evidence_mean = statistics.fmean(evidence_confidences) if evidence_confidences else 0.0
        completeness = present_periods / len(periods)
        row_confidence = round(0.75 * evidence_mean + 0.25 * completeness, 6)
        row_tokens = label_tokens + list(data["line"].tokens)
        reconstructed.append(
            (
                data["center_y"],
                {
                    "row_index": data_row_index + 1,
                    "row_type": row_type,
                    "label": label_text or None,
                    "note_reference": note_reference,
                    "cells": cells,
                    "bbox": _bbox(row_tokens),
                    "confidence": row_confidence,
                    "source": _source(page_number, _bbox(row_tokens), label_text),
                },
            )
        )

    for index, line in enumerate(label_lines):
        if index in used_labels:
            continue
        reconstructed.append(
            (
                line.center_y,
                {
                    "row_index": None,
                    "row_type": "section_header",
                    "label": line.text,
                    "note_reference": None,
                    "cells": [_line_cell(line, "section_header", page_number)],
                    "bbox": _bbox(line.tokens),
                    "confidence": round(line.confidence, 6),
                    "source": _source(page_number, _bbox(line.tokens), line.text),
                },
            )
        )

    reconstructed.sort(key=lambda item: item[0])
    rows = [row for _, row in reconstructed]
    for index, row in enumerate(rows, start=1):
        row["row_index"] = index

    table_id = f"summary-p{page_number}"
    _assign_row_relationships(table_id, rows)
    for row in rows:
        for cell in row.get("cells", []):
            resolution = cell.get("normalization_resolution")
            if not resolution:
                continue
            warnings.append(
                {
                    "code": "evidence_resolved_financial_value",
                    "row_id": row["row_id"],
                    "period": cell.get("period"),
                    "raw_text": cell.get("raw_text"),
                    "parser_normalized_value": cell.get("parser_normalized_value"),
                    "selected_value": cell.get("normalized_value"),
                    "method": resolution.get("method"),
                    "target_row_id": resolution.get("target_row_id"),
                }
            )

    title_line = next(
        (line for line in lines if "KONSOLİDE" in line.text.upper()),
        None,
    )
    title_lines = [title_line] if title_line else []
    if title_line is not None:
        title_index = lines.index(title_line)
        if title_index > 0:
            previous_line = lines[title_index - 1]
            vertical_gap = title_line.top - previous_line.bottom
            previous_upper = previous_line.text.upper()
            if (
                vertical_gap <= max(40, (title_line.bottom - title_line.top) * 2)
                and ("DENET" in previous_upper or "TARİH" in previous_upper)
            ):
                title_lines.insert(0, previous_line)
    title_text = " ".join(line.text for line in title_lines) or None
    title_tokens = [token for line in title_lines for token in line.tokens]
    currency_line = next(
        (line for line in lines if "(TL)" in line.text.upper()),
        None,
    )
    page_tokens = [token for row in data_rows for token in row["line"].tokens]
    assigned_rows = sum(1 for _, row in reconstructed if row["row_type"] != "section_header" and row["label"])
    financial_rows = sum(1 for _, row in reconstructed if row["row_type"] != "section_header")
    assigned_cells = sum(
        1
        for _, row in reconstructed
        for cell in row["cells"]
        if cell["role"] == "data_cell" and cell["bbox"] is not None
    )
    expected_cells = financial_rows * len(periods)
    row_assignment_rate = assigned_rows / financial_rows if financial_rows else 0.0
    period_assignment_rate = assigned_cells / expected_cells if expected_cells else 0.0
    mean_row_confidence = statistics.fmean(
        row["confidence"] for _, row in reconstructed if row["row_type"] != "section_header"
    )
    period_header_confidence = _confidence(year_tokens)
    table_confidence = round(
        statistics.fmean(
            [
                period_header_confidence,
                row_assignment_rate,
                period_assignment_rate,
                mean_row_confidence,
            ]
        ),
        6,
    )
    table_bbox_tokens = (
        title_tokens
        + list(header_line.tokens)
        + [token for line in label_lines for token in line.tokens]
        + page_tokens
    )
    printed_page_number = _find_printed_page_number(lines, last_data_y)
    period_columns = [
        {
            "column_id": f"{table_id}:column-period-{str(token['text'])}",
            "column_index": index,
            "role": "data_column",
            "period": str(token["text"]),
            "raw_text": str(token["text"]),
            "bbox": _bbox([token]),
            "confidence": round(float(token["confidence"]), 6),
            "source": _source(page_number, _bbox([token]), str(token["text"])),
        }
        for index, token in enumerate(year_tokens, start=3)
    ]
    columns = [
        {
            "column_id": f"{table_id}:column-row-header",
            "column_index": 1,
            "role": "row_header",
            "name": "line_item",
            "header_status": "implicit_layout_column",
        },
        {
            "column_id": f"{table_id}:column-note-reference",
            "column_index": 2,
            "role": "note_reference",
            "name": "note_reference",
            "header_status": "extracted",
            "raw_text": " ".join(str(token["text"]) for token in note_header_tokens),
            "bbox": _bbox(note_header_tokens),
            "confidence": _confidence(note_header_tokens),
            "source": _source(
                page_number,
                _bbox(note_header_tokens),
                " ".join(str(token["text"]) for token in note_header_tokens),
            ),
        },
        *period_columns,
    ]
    return {
        "table_id": table_id,
        "table_type": "summary_financial_statement",
        "title": title_text,
        "page": {
            "pdf_page_number": page_number,
            "page_index": page_number - 1,
            "printed_page_number": printed_page_number,
        },
        "bbox": _bbox(table_bbox_tokens),
        "currency": {
            "code": "TRY" if currency_line else None,
            "raw_text": currency_line.text if currency_line else None,
            "source": _source(
                page_number,
                _bbox(currency_line.tokens) if currency_line else None,
                currency_line.text if currency_line else "",
            ),
        },
        "periods": [
            {
                "role": "column_header",
                "raw_text": str(token["text"]),
                "bbox": _bbox([token]),
                "confidence": round(float(token["confidence"]), 6),
                "source": _source(page_number, _bbox([token]), str(token["text"])),
            }
            for token in year_tokens
        ],
        "columns": columns,
        "rows": rows,
        "quality": {
            "period_header_confidence": period_header_confidence,
            "row_label_assignment_rate": round(row_assignment_rate, 6),
            "period_cell_assignment_rate": round(period_assignment_rate, 6),
        },
        "confidence": table_confidence,
        "warnings": warnings,
    }


def extract_summary_document(ocr_output: dict[str, Any]) -> dict[str, Any]:
    """Extract all configured summary pages and aggregate document metadata."""

    tables = [extract_summary_page(page) for page in ocr_output["pages"]]
    company_line = _group_lines(ocr_output["pages"][0]["tokens"])[0]
    periods: list[str] = []
    for table in tables:
        for period in table["periods"]:
            if period["raw_text"] not in periods:
                periods.append(period["raw_text"])
    has_warnings = any(table["warnings"] for table in tables)
    return {
        "stage": "summary_structure",
        "status": "completed_with_warnings" if has_warnings else "completed",
        "document_metadata": {
            "company_name": company_line.text,
            "reporting_periods": periods,
            "currency": "TRY" if all(table["currency"]["code"] == "TRY" for table in tables) else None,
            "company_source": _source(
                int(ocr_output["pages"][0]["pdf_page_number"]),
                _bbox(company_line.tokens),
                company_line.text,
            ),
        },
        "tables": tables,
    }
