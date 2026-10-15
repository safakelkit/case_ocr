# Bu dosya, kalite kapılarını, finansal kontrolleri ve kanıta dayalı nihai güven değerlerini hesaplamak için kullanılır.
"""Evidence-based validation, quality gates, and final relation confidence."""

from __future__ import annotations

import math
import re
import statistics
from typing import Any, Iterable

from ykt_case.config import PipelineConfig, QualityGate


def _result(
    check_id: str,
    group: str,
    status: str,
    message: str,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if status not in {"passed", "failed", "incomplete", "not_applicable"}:
        raise ValueError(f"unsupported validation status: {status}")
    return {
        "check_id": check_id,
        "group": group,
        "status": status,
        "message": message,
        "evidence": evidence or {},
    }


def _all_note_tables(note_output: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        table
        for note in note_output.get("notes", [])
        for table in note.get("tables", [])
    ]


def _all_rows_by_id(
    summary_output: dict[str, Any], note_output: dict[str, Any]
) -> tuple[set[str], set[str]]:
    summary_ids = {
        str(row.get("row_id") or f"{table['table_id']}:row-{row['row_index']}")
        for table in summary_output.get("tables", [])
        for row in table.get("rows", [])
    }
    note_ids = {
        str(row.get("row_id") or f"{table['table_id']}:row-{row['row_index']}")
        for table in _all_note_tables(note_output)
        for row in table.get("rows", [])
    }
    return summary_ids, note_ids


def validate_structure(
    config: PipelineConfig,
    summary_output: dict[str, Any],
    note_output: dict[str, Any],
    relation_output: dict[str, Any],
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    expected_pages = set(range(config.summary_pages.start, config.summary_pages.end + 1))
    actual_pages = {
        int(table["page"]["pdf_page_number"])
        for table in summary_output.get("tables", [])
    }
    checks.append(
        _result(
            "summary_page_coverage",
            "structural",
            "passed" if expected_pages.issubset(actual_pages) else "failed",
            "Configured summary pages must be represented by structured tables.",
            {"expected": sorted(expected_pages), "actual": sorted(actual_pages)},
        )
    )

    expected_periods = set(
        str(value)
        for value in summary_output.get("document_metadata", {}).get(
            "reporting_periods", []
        )
    )
    period_failures = []
    for table in summary_output.get("tables", []):
        actual = {str(period.get("raw_text")) for period in table.get("periods", [])}
        if not expected_periods or actual != expected_periods:
            period_failures.append(
                {
                    "table_id": table.get("table_id"),
                    "expected": sorted(expected_periods),
                    "actual": sorted(actual),
                }
            )
    checks.append(
        _result(
            "summary_period_sets",
            "structural",
            "passed" if not period_failures else "failed",
            "Every summary table must expose the document reporting periods exactly once.",
            {"violations": period_failures},
        )
    )

    notes_by_number = {
        int(note["note_number"]): note for note in note_output.get("notes", [])
    }
    missing_notes = [note for note in config.target_notes if note not in notes_by_number]
    empty_notes = [
        note
        for note in config.target_notes
        if note in notes_by_number and not notes_by_number[note].get("tables")
    ]
    checks.append(
        _result(
            "configured_note_coverage",
            "structural",
            "passed" if not missing_notes and not empty_notes else "failed",
            "Every configured note must exist and contain at least one structured table.",
            {"missing_notes": missing_notes, "notes_without_tables": empty_notes},
        )
    )

    summary_ids, note_ids = _all_rows_by_id(summary_output, note_output)
    invalid_relations = []
    for relation in relation_output.get("relations", []):
        missing_selected = [
            row_id
            for row_id in relation.get("selected_note_row_ids", [])
            if row_id not in note_ids
        ]
        if relation.get("summary_row_id") not in summary_ids or missing_selected:
            invalid_relations.append(
                {
                    "relation_id": relation.get("relation_id"),
                    "summary_row_exists": relation.get("summary_row_id") in summary_ids,
                    "missing_selected_note_rows": missing_selected,
                }
            )
    checks.append(
        _result(
            "relation_referential_integrity",
            "structural",
            "passed" if not invalid_relations else "failed",
            "Relation identifiers must resolve to emitted summary and note rows.",
            {"violations": invalid_relations},
        )
    )
    return checks


def _walk(value: Any, path: str = "$") -> Iterable[tuple[str, str, Any]]:
    if isinstance(value, dict):
        for key, nested in value.items():
            current = f"{path}.{key}"
            yield current, key, nested
            yield from _walk(nested, current)
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            yield from _walk(nested, f"{path}[{index}]")


def validate_format(*artifacts: dict[str, Any]) -> list[dict[str, Any]]:
    confidence_violations = []
    bbox_violations = []
    numeric_violations = []
    for artifact_index, artifact in enumerate(artifacts):
        for path, key, value in _walk(artifact, f"$[{artifact_index}]"):
            if key == "confidence" and (
                not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or not 0.0 <= float(value) <= 1.0
            ):
                confidence_violations.append({"path": path, "value": value})
            if key == "bbox" and isinstance(value, dict):
                required = {"left", "top", "width", "height"}
                if set(value) != required or any(
                    not isinstance(value.get(field), int) or value.get(field, -1) < 0
                    for field in required
                ):
                    bbox_violations.append({"path": path, "value": value})
            if key == "numeric_status" and isinstance(value, str):
                parent_path = path.rsplit(".", 1)[0]
                # Recovering the parent through a second walk keeps this validator generic.
                # Numeric coherence is also checked directly below on known cell collections.
                if value not in {
                    "value",
                    "percentage",
                    "percentage_range",
                    "dash",
                    "blank",
                    "invalid",
                }:
                    numeric_violations.append(
                        {"path": parent_path, "reason": "unknown_numeric_status", "value": value}
                    )

    cells = []
    for artifact in artifacts:
        for path, key, value in _walk(artifact):
            if key == "cells" and isinstance(value, list):
                cells.extend((path, cell) for cell in value if isinstance(cell, dict))
    for path, cell in cells:
        status = cell.get("numeric_status")
        if status is None:
            continue
        normalized = cell.get("normalized_value")
        if status in {"value", "percentage"} and not isinstance(normalized, (int, float)):
            numeric_violations.append(
                {"path": path, "reason": "numeric_status_requires_value", "cell": cell}
            )
        if status == "percentage" and isinstance(normalized, (int, float)) and not (
            0.0 <= float(normalized) <= 100.0
        ):
            numeric_violations.append(
                {"path": path, "reason": "percentage_out_of_range", "cell": cell}
            )
        if status == "percentage_range":
            valid_range = (
                isinstance(normalized, dict)
                and set(normalized) == {"min", "max"}
                and all(
                    isinstance(normalized.get(bound), (int, float))
                    and math.isfinite(float(normalized[bound]))
                    for bound in ("min", "max")
                )
                and float(normalized["min"]) <= float(normalized["max"])
                and 0.0 <= float(normalized["min"])
                and float(normalized["max"]) <= 100.0
            )
            if not valid_range:
                numeric_violations.append(
                    {"path": path, "reason": "percentage_range_requires_bounds", "cell": cell}
                )
        if status in {"dash", "blank", "invalid"} and normalized is not None:
            numeric_violations.append(
                {"path": path, "reason": "non_value_status_requires_null", "cell": cell}
            )

    return [
        _result(
            "confidence_format",
            "format",
            "passed" if not confidence_violations else "failed",
            "Every confidence must be finite and in [0, 1].",
            {"violations": confidence_violations},
        ),
        _result(
            "bounding_box_format",
            "format",
            "passed" if not bbox_violations else "failed",
            "Every bounding box must contain non-negative integer geometry.",
            {"violations": bbox_violations},
        ),
        _result(
            "numeric_representation",
            "format",
            "passed" if not numeric_violations else "failed",
            "Numeric status and normalized value must remain semantically coherent.",
            {"violations": numeric_violations},
        ),
    ]


def _cell_by_column(row: dict[str, Any], column_index: int) -> dict[str, Any] | None:
    return next(
        (
            cell
            for cell in row.get("cells", [])
            if int(cell.get("column_index", -1)) == column_index
        ),
        None,
    )


def _financial_value(cell: dict[str, Any] | None) -> tuple[bool, float]:
    if cell is None:
        return False, 0.0
    status = cell.get("numeric_status")
    if status == "dash":
        return True, 0.0
    if status == "value" and isinstance(cell.get("normalized_value"), (int, float)):
        return True, float(cell["normalized_value"])
    return False, 0.0


def _normalized_label(value: Any) -> str:
    text = str(value or "").casefold().replace("ı", "i")
    return " ".join(re.findall(r"[a-z0-9]+", text))


def _balance_sheet_check(summary_output: dict[str, Any] | None) -> dict[str, Any]:
    rows = [
        row
        for table in (summary_output or {}).get("tables", [])
        for row in table.get("rows", [])
    ]
    assets = next(
        (row for row in rows if _normalized_label(row.get("label")) == "toplam varliklar"),
        None,
    )
    sources = next(
        (row for row in rows if _normalized_label(row.get("label")) == "toplam kaynaklar"),
        None,
    )
    if assets is None or sources is None:
        return _result(
            "balance_sheet_total_equality",
            "financial",
            "not_applicable",
            "Balance-sheet total rows were not both available.",
        )
    asset_cells = {
        str(cell.get("period")): cell
        for cell in assets.get("cells", [])
        if cell.get("role") == "data_cell"
    }
    source_cells = {
        str(cell.get("period")): cell
        for cell in sources.get("cells", [])
        if cell.get("role") == "data_cell"
    }
    periods = sorted(set(asset_cells) | set(source_cells))
    evidence = []
    incomplete = False
    failed = False
    for period in periods:
        asset_ok, asset_value = _financial_value(asset_cells.get(period))
        source_ok, source_value = _financial_value(source_cells.get(period))
        if not asset_ok or not source_ok:
            incomplete = True
            evidence.append({"period": period, "status": "incomplete"})
            continue
        difference = asset_value - source_value
        failed = failed or difference != 0.0
        evidence.append(
            {
                "period": period,
                "assets": asset_value,
                "liabilities_and_equity": source_value,
                "difference": difference,
            }
        )
    status = "failed" if failed else "incomplete" if incomplete else "passed"
    return _result(
        "balance_sheet_total_equality",
        "financial",
        status,
        "Total assets must equal total liabilities and equity for every reporting period.",
        {"periods": evidence},
    )


def validate_financial(
    note_output: dict[str, Any],
    relation_output: dict[str, Any],
    summary_output: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = [_balance_sheet_check(summary_output)]
    applicable = 0
    for table in _all_note_tables(note_output):
        rows = table.get("rows", [])
        total_position = next(
            (index for index, row in enumerate(rows) if row.get("row_type") == "total"),
            None,
        )
        if total_position is None or total_position == 0:
            checks.append(
                _result(
                    f"{table['table_id']}:detail_sum",
                    "financial",
                    "not_applicable",
                    "No detail-to-total reconciliation pattern was detected.",
                )
            )
            continue
        applicable += 1
        detail_rows = rows[:total_position]
        total_row = rows[total_position]
        for column in table.get("columns", []):
            column_index = int(column["column_index"])
            detail_values = [
                _financial_value(_cell_by_column(row, column_index))
                for row in detail_rows
            ]
            total_ok, total_value = _financial_value(
                _cell_by_column(total_row, column_index)
            )
            check_id = f"{table['table_id']}:column-{column_index}:detail_sum"
            if not total_ok or not all(valid for valid, _ in detail_values):
                checks.append(
                    _result(
                        check_id,
                        "financial",
                        "incomplete",
                        "Reconciliation could not be evaluated without guessing damaged cells.",
                        {
                            "column_header": column.get("raw_text"),
                            "detail_value_statuses": [valid for valid, _ in detail_values],
                            "total_value_available": total_ok,
                        },
                    )
                )
                continue
            expected = math.fsum(value for _, value in detail_values)
            difference = total_value - expected
            checks.append(
                _result(
                    check_id,
                    "financial",
                    "passed" if difference == 0 else "failed",
                    "The first total row must equal the exact sum of preceding detail rows.",
                    {
                        "column_header": column.get("raw_text"),
                        "expected": expected,
                        "actual": total_value,
                        "difference": difference,
                    },
                )
            )
    if not applicable:
        checks.append(
            _result(
                "note_detail_sum_reconciliation",
                "financial",
                "not_applicable",
                "No note table exposed an applicable detail-to-total pattern.",
            )
        )

    for relation in relation_output.get("relations", []):
        coverage = float(relation.get("matched_value_coverage", 0.0))
        checks.append(
            _result(
                f"{relation['relation_id']}:value_coverage",
                "financial",
                "passed" if coverage == 1.0 else "failed",
                "Selected note evidence must cover every normalized summary-period value.",
                {
                    "summary_row_id": relation.get("summary_row_id"),
                    "coverage": coverage,
                    "unmatched_periods": relation.get("unmatched_periods", []),
                },
            )
        )
    return checks


def aggregate_relation_confidence(
    relation_output: dict[str, Any], baseline_output: dict[str, Any]
) -> list[dict[str, Any]]:
    baseline_by_summary = {
        (relation["summary_row_id"], int(relation["note_number"])): relation
        for relation in baseline_output.get("relations", [])
    }
    results = []
    for relation in relation_output.get("relations", []):
        selected_ids = set(relation.get("selected_note_row_ids", []))
        selected_candidates = [
            candidate
            for candidate in relation.get("top_candidates", [])
            if candidate.get("note_row_id") in selected_ids
        ]
        extraction_quality = (
            statistics.fmean(
                float(candidate["features"].get("evidence_quality", 0.0))
                for candidate in selected_candidates
            )
            if selected_candidates
            else 0.0
        )
        baseline_relation = baseline_by_summary.get(
            (relation.get("summary_row_id"), int(relation.get("note_number", -1)))
        )
        method_agreement = (
            1.0
            if selected_ids
            and baseline_relation is not None
            and set(baseline_relation.get("selected_note_row_ids", [])) == selected_ids
            else 0.0
        )
        matcher_confidence = float(relation.get("confidence", 0.0))
        numeric_coverage = float(relation.get("matched_value_coverage", 0.0))
        pre_penalty = (
            0.35 * matcher_confidence
            + 0.25 * numeric_coverage
            + 0.20 * extraction_quality
            + 0.20 * method_agreement
        )
        penalties = []
        factor = 1.0
        if relation.get("ambiguous"):
            factor *= 0.90
            penalties.append({"reason": "ambiguous_numeric_alternatives", "factor": 0.90})
        if relation_output.get("fallback_used"):
            factor *= 0.85
            penalties.append({"reason": "semantic_fallback_used", "factor": 0.85})
        if relation.get("status") != "matched":
            factor *= 0.80
            penalties.append({"reason": "relation_not_fully_matched", "factor": 0.80})
        final_confidence = round(min(1.0, max(0.0, pre_penalty * factor)), 6)
        results.append(
            {
                "relation_id": relation.get("relation_id"),
                "summary_row_id": relation.get("summary_row_id"),
                "method": "evidence_aggregated_confidence_v1",
                "components": {
                    "matcher_confidence": round(matcher_confidence, 6),
                    "numeric_coverage": round(numeric_coverage, 6),
                    "selected_extraction_quality": round(extraction_quality, 6),
                    "baseline_semantic_agreement": method_agreement,
                },
                "weights": {
                    "matcher_confidence": 0.35,
                    "numeric_coverage": 0.25,
                    "selected_extraction_quality": 0.20,
                    "baseline_semantic_agreement": 0.20,
                },
                "penalties": penalties,
                "pre_penalty_confidence": round(pre_penalty, 6),
                "final_confidence": final_confidence,
                "interpretation": (
                    "Evidence aggregation score for review prioritization; not a calibrated probability."
                ),
            }
        )
    return results


def _metric_values(
    summary_ocr: dict[str, Any],
    summary_output: dict[str, Any],
    note_location: dict[str, Any],
    note_output: dict[str, Any],
    relation_output: dict[str, Any],
    relation_confidences: list[dict[str, Any]],
    validations: list[dict[str, Any]],
) -> dict[str, float]:
    summary_tables = summary_output.get("tables", [])
    note_tables = _all_note_tables(note_output)
    expected_periods = set(
        str(value)
        for value in summary_output.get("document_metadata", {}).get(
            "reporting_periods", []
        )
    )
    period_coverage = statistics.fmean(
        1.0
        if {str(period.get("raw_text")) for period in table.get("periods", [])}
        == expected_periods
        else 0.0
        for table in summary_tables
    )
    upstream_warning_count = sum(
        len(table.get("warnings", [])) for table in summary_tables + note_tables
    ) + (1 if relation_output.get("fallback_used") else 0)
    return {
        "summary_ocr_mean_confidence": min(
            float(page["ocr_confidence"]["mean"])
            for page in summary_ocr.get("pages", [])
        ),
        "summary_ocr_p10_confidence": min(
            float(page["ocr_confidence"]["p10"])
            for page in summary_ocr.get("pages", [])
        ),
        "period_header_coverage": period_coverage,
        "summary_row_label_assignment_rate": min(
            float(table["quality"]["row_label_assignment_rate"])
            for table in summary_tables
        ),
        "summary_period_cell_assignment_rate": min(
            float(table["quality"]["period_cell_assignment_rate"])
            for table in summary_tables
        ),
        "note_location_confidence": min(
            float(location["confidence"])
            for location in note_location.get("locations", [])
        ),
        "note_data_cell_assignment_rate": min(
            float(table["quality"]["data_cell_assignment_rate"])
            for table in note_tables
        ),
        "note_value_parse_success_rate": min(
            float(table["quality"]["value_parse_success_rate"])
            for table in note_tables
        ),
        "relation_value_coverage": min(
            float(relation.get("matched_value_coverage", 0.0))
            for relation in relation_output.get("relations", [])
        ),
        "minimum_final_relation_confidence": min(
            float(item["final_confidence"]) for item in relation_confidences
        ),
        "structural_failure_count": float(
            sum(
                item["status"] == "failed"
                for item in validations
                if item["group"] == "structural"
            )
        ),
        "format_violation_count": float(
            sum(
                len(item["evidence"].get("violations", []))
                for item in validations
                if item["group"] == "format"
            )
        ),
        "financial_reconciliation_failure_count": float(
            sum(
                item["status"] == "failed"
                for item in validations
                if item["group"] == "financial"
            )
        ),
        "financial_reconciliation_incomplete_count": float(
            sum(
                item["status"] == "incomplete"
                for item in validations
                if item["group"] == "financial"
            )
        ),
        "upstream_warning_count": float(upstream_warning_count),
    }


def evaluate_quality_gates(
    gates: tuple[QualityGate, ...], metrics: dict[str, float]
) -> list[dict[str, Any]]:
    results = []
    for gate in gates:
        if gate.name not in metrics:
            raise ValueError(f"quality gate metric is unavailable: {gate.name}")
        observed = float(metrics[gate.name])
        passed = (
            observed >= gate.threshold
            if gate.comparator == "gte"
            else observed <= gate.threshold
        )
        results.append(
            {
                "gate": gate.name,
                "observed": round(observed, 6),
                "threshold": gate.threshold,
                "comparator": gate.comparator,
                "passed": passed,
                "configured_action": gate.action,
                "outcome": "continue" if passed else gate.action,
                "rationale": gate.rationale,
            }
        )
    return results


def validate_pipeline_outputs(
    config: PipelineConfig,
    summary_ocr: dict[str, Any],
    summary_output: dict[str, Any],
    note_location: dict[str, Any],
    note_output: dict[str, Any],
    baseline_output: dict[str, Any],
    relation_output: dict[str, Any],
) -> dict[str, Any]:
    structural = validate_structure(config, summary_output, note_output, relation_output)
    formatting = validate_format(summary_output, note_output, relation_output)
    financial = validate_financial(note_output, relation_output, summary_output)
    validations = structural + formatting + financial
    relation_confidences = aggregate_relation_confidence(
        relation_output, baseline_output
    )
    metrics = _metric_values(
        summary_ocr,
        summary_output,
        note_location,
        note_output,
        relation_output,
        relation_confidences,
        validations,
    )
    gate_results = evaluate_quality_gates(config.quality_gates, metrics)
    stopped = [
        gate
        for gate in gate_results
        if not gate["passed"] and gate["configured_action"] == "stop"
    ]
    warnings = [
        gate
        for gate in gate_results
        if not gate["passed"]
        and gate["configured_action"] == "continue_with_warning"
    ]
    status = "failed" if stopped else "completed_with_warnings" if warnings else "completed"
    return {
        "stage": "confidence_and_validation",
        "status": status,
        "validation_method_version": "1.0",
        "metrics": {name: round(value, 6) for name, value in metrics.items()},
        "quality_gates": gate_results,
        "validation_summary": {
            "passed": sum(item["status"] == "passed" for item in validations),
            "failed": sum(item["status"] == "failed" for item in validations),
            "incomplete": sum(item["status"] == "incomplete" for item in validations),
            "not_applicable": sum(
                item["status"] == "not_applicable" for item in validations
            ),
            "stop_gate_failures": len(stopped),
            "warning_gate_failures": len(warnings),
        },
        "validations": {
            "structural": structural,
            "format": formatting,
            "financial": financial,
        },
        "relation_confidences": relation_confidences,
        "limitations": [
            "Quality thresholds are transparent engineering thresholds, not statistically calibrated probabilities.",
            "The reviewed relation set contains only two examples, so confidence is intended for evidence aggregation and review prioritization.",
            "Incomplete financial checks preserve OCR uncertainty instead of substituting expected values.",
        ],
    }
