# Bu dosya, tüm pipeline aşamalarını sıralamak ve sonuç, manifest ile olay günlüğünü üretmek için kullanılır.
"""One-command orchestration, reproducible run manifest, and final JSON output."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path
import platform
import random
import shutil
import subprocess
import sys
import time
from typing import Any, Callable

from ykt_case.config import PipelineConfig
from ykt_case.pipeline import (
    run_baseline_matching,
    run_note_extraction,
    run_note_location,
    run_semantic_matching,
    run_summary_ocr,
    run_summary_structure,
    run_validation,
)
from ykt_case.progress import progress_bar


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _command_version(command: list[str]) -> str | None:
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    combined = (result.stdout or result.stderr).strip()
    return combined.splitlines()[0] if combined else None


def _git_state() -> dict[str, Any]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return {"commit": None, "dirty": None}
    return {
        "commit": commit.stdout.strip() if commit.returncode == 0 else None,
        "dirty": bool(status.stdout.strip()) if status.returncode == 0 else None,
    }


def _package_versions() -> dict[str, str | None]:
    packages = [
        "ykt-case",
        "fastembed",
        "onnxruntime",
        "numpy",
        "tokenizers",
        "tqdm",
    ]
    result = {}
    for package in packages:
        try:
            result[package] = version(package)
        except PackageNotFoundError:
            result[package] = None
    return result


def _write_event(log_path: Path, event: dict[str, Any]) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, ensure_ascii=False) + "\n")


def _warning_records(
    summary_output: dict[str, Any],
    note_output: dict[str, Any],
    validation_output: dict[str, Any],
) -> list[dict[str, Any]]:
    warnings = []
    for table in summary_output.get("tables", []):
        for warning in table.get("warnings", []):
            warnings.append(
                {"stage": "summary_structure", "table_id": table["table_id"], **warning}
            )
    for note in note_output.get("notes", []):
        for table in note.get("tables", []):
            for warning in table.get("warnings", []):
                warnings.append(
                    {"stage": "note_extraction", "table_id": table["table_id"], **warning}
                )
    for gate in validation_output.get("quality_gates", []):
        if not gate.get("passed"):
            warnings.append(
                {
                    "stage": "confidence_and_validation",
                    "code": "quality_gate_failed",
                    "gate": gate["gate"],
                    "outcome": gate["outcome"],
                    "observed": gate["observed"],
                    "threshold": gate["threshold"],
                }
            )
    return warnings


def _gate_threshold(config: PipelineConfig, name: str) -> float | None:
    for gate in config.quality_gates:
        if gate.name == name:
            return gate.threshold
    return None


def _set_review_fields(record: dict[str, Any], flags: list[str]) -> None:
    record["quality_flags"] = sorted(set(flags))
    record["review_required"] = bool(record["quality_flags"])


def _annotate_extraction_review(
    tables: list[dict[str, Any]], confidence_threshold: float | None
) -> None:
    """Add uniform, evidence-derived review markers without changing raw evidence."""

    for table in tables:
        table_flags: list[str] = []
        if (
            confidence_threshold is not None
            and float(table.get("confidence", 0.0)) < confidence_threshold
        ):
            table_flags.append("low_confidence")
        if table.get("warnings"):
            table_flags.append("extraction_warnings")
        for row in table.get("rows", []):
            row_flags: list[str] = []
            if (
                confidence_threshold is not None
                and float(row.get("confidence", 0.0)) < confidence_threshold
            ):
                row_flags.append("low_confidence")
            if row.get("row_type") != "section_header" and not row.get("label"):
                row_flags.append("missing_row_label")
            if row.get("aggregation_status") == "unresolved":
                row_flags.append("unresolved_aggregation")
            for cell in row.get("cells", []):
                cell_flags: list[str] = []
                if (
                    confidence_threshold is not None
                    and float(cell.get("confidence", 0.0)) < confidence_threshold
                ):
                    cell_flags.append("low_confidence")
                if cell.get("numeric_status") == "invalid":
                    cell_flags.append("invalid_numeric_value")
                if (
                    cell.get("bbox") is None
                    and cell.get("numeric_status") not in {"blank", None}
                ):
                    cell_flags.append("missing_bbox")
                _set_review_fields(cell, cell_flags)
                if cell["review_required"]:
                    row_flags.append("contains_review_cell")
            _set_review_fields(row, row_flags)
            if row["review_required"]:
                table_flags.append("contains_review_row")
        _set_review_fields(table, table_flags)


def _annotate_relation_review(
    relations: list[dict[str, Any]], threshold: float | None, fallback_used: bool
) -> None:
    for relation in relations:
        flags: list[str] = []
        if threshold is not None and float(relation.get("confidence", 0.0)) < threshold:
            flags.append("low_relation_confidence")
        if relation.get("ambiguous"):
            flags.append("ambiguous_numeric_alternatives")
        if float(relation.get("matched_value_coverage", 0.0)) < 1.0:
            flags.append("incomplete_value_coverage")
        if relation.get("status") != "matched":
            flags.append("relation_not_fully_matched")
        if fallback_used:
            flags.append("semantic_fallback_used")
        _set_review_fields(relation, flags)


def build_final_output(
    config: PipelineConfig,
    summary_output: dict[str, Any],
    note_output: dict[str, Any],
    baseline_output: dict[str, Any],
    semantic_output: dict[str, Any],
    validation_output: dict[str, Any],
    manifest_path: Path,
) -> dict[str, Any]:
    """Assemble delivery JSON without evaluation labels or manual answers."""

    confidence_by_relation = {
        item["relation_id"]: item
        for item in validation_output.get("relation_confidences", [])
    }
    summary_tables = deepcopy(summary_output.get("tables", []))
    notes = deepcopy(note_output.get("notes", []))
    extraction_threshold = _gate_threshold(config, "summary_ocr_p10_confidence")
    relation_threshold = _gate_threshold(config, "minimum_final_relation_confidence")
    _annotate_extraction_review(summary_tables, extraction_threshold)
    for note in notes:
        _annotate_extraction_review(note.get("tables", []), extraction_threshold)

    final_relations = []
    for relation in semantic_output.get("relations", []):
        item = deepcopy(relation)
        confidence = confidence_by_relation.get(relation["relation_id"])
        item["matching_confidence"] = item.pop("confidence", 0.0)
        item["confidence"] = (
            confidence["final_confidence"] if confidence is not None else 0.0
        )
        item["confidence_evidence"] = confidence
        final_relations.append(item)
    _annotate_relation_review(
        final_relations,
        relation_threshold,
        bool(semantic_output.get("fallback_used", False)),
    )
    warnings = _warning_records(summary_output, note_output, validation_output)
    return {
        "schema_version": "1.0",
        "status": validation_output["status"],
        "document": summary_output.get("document_metadata", {}),
        "source": {
            "file_name": config.source_pdf.name,
            "sha256": sha256_file(config.source_pdf),
            "configured_summary_pages": {
                "start": config.summary_pages.start,
                "end": config.summary_pages.end,
            },
            "configured_target_notes": list(config.target_notes),
        },
        "summary_tables": summary_tables,
        "notes": notes,
        "matching": {
            "selected_method": semantic_output.get("method"),
            "fallback_used": semantic_output.get("fallback_used", False),
            "baseline_method": baseline_output.get("method"),
            "relations": final_relations,
        },
        "validation": {
            "method_version": validation_output.get("validation_method_version"),
            "status": validation_output.get("status"),
            "metrics": validation_output.get("metrics"),
            "quality_gates": validation_output.get("quality_gates"),
            "summary": validation_output.get("validation_summary"),
            "checks": validation_output.get("validations"),
            "limitations": validation_output.get("limitations"),
        },
        "warnings": warnings,
        "review_policy": {
            "record_levels": ["table", "row", "cell", "relation"],
            "extraction_confidence_threshold": extraction_threshold,
            "relation_confidence_threshold": relation_threshold,
            "threshold_source": "configured_quality_gates",
        },
        "run_manifest": str(manifest_path),
        "evaluation_labels_used_at_runtime": False,
    }


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def run_end_to_end(config: PipelineConfig, config_path: Path) -> tuple[Path, Path]:
    """Run all mandatory runtime stages, producing final JSON and a run manifest."""

    random.seed(config.random_seed)
    run_started = _utc_now()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    manifest_dir = config.work_dir / "manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / f"run-{run_id}.json"
    log_path = config.work_dir / "logs" / f"run-{run_id}.jsonl"
    delivery_manifest_path = config.output_path.parent / "run_manifest.json"
    delivery_log_path = config.output_path.parent / "run_events.jsonl"
    if log_path.exists():
        log_path.unlink()

    manifest: dict[str, Any] = {
        "schema_version": "1.0",
        "run_id": run_id,
        "status": "running",
        "started_at": run_started,
        "finished_at": None,
        "random_seed": config.random_seed,
        "determinism": "No stochastic runtime algorithm is used; seed is recorded for future-compatible stages.",
        "source": {
            "file_name": config.source_pdf.name,
            "size_bytes": config.source_pdf.stat().st_size,
            "sha256": sha256_file(config.source_pdf),
        },
        "configuration": {
            "file_name": config_path.name,
            "sha256": sha256_file(config_path),
        },
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "packages": _package_versions(),
            "system_dependencies": {
                "tesseract": _command_version(["tesseract", "--version"]),
                "pdftoppm": _command_version(["pdftoppm", "-v"]),
            },
        },
        "git": _git_state(),
        "event_log": str(delivery_log_path),
        "stages": [],
        "models": [],
        "quality_gates": [],
        "validation_summary": None,
        "fallback_events": [],
        "error": None,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    stages: list[tuple[str, str, Callable[[PipelineConfig], Path]]] = [
        ("summary_ocr", "Özet tablo OCR", run_summary_ocr),
        ("summary_structure", "Özet tablo yapılandırma", run_summary_structure),
        ("note_location", "Dipnot bulma", run_note_location),
        ("note_extraction", "Dipnot tablo çıkarımı", run_note_extraction),
        ("relation_matching_baseline", "Baseline eşleştirme", run_baseline_matching),
        ("relation_matching_semantic", "Embedding eşleştirme", run_semantic_matching),
        ("confidence_and_validation", "Güven ve validasyon", run_validation),
    ]
    outputs: dict[str, Path] = {}
    try:
        with progress_bar(
            total=len(stages), description="Pipeline", unit="aşama"
        ) as stage_progress:
            for stage_name, stage_label, runner in stages:
                stage_progress.set_description_str(f"Pipeline · {stage_label}")
                stage_started = _utc_now()
                start = time.perf_counter()
                _write_event(
                    log_path,
                    {"timestamp": stage_started, "event": "stage_started", "stage": stage_name},
                )
                output_path = runner(config)
                elapsed = round(time.perf_counter() - start, 6)
                stage_output = _read_json(output_path)
                record = {
                    "stage": stage_name,
                    "status": stage_output.get("status", "completed"),
                    "started_at": stage_started,
                    "finished_at": _utc_now(),
                    "duration_seconds": elapsed,
                    "output": str(output_path),
                    "output_sha256": sha256_file(output_path),
                }
                manifest["stages"].append(record)
                outputs[stage_name] = output_path
                if stage_name == "relation_matching_semantic":
                    model = stage_output.get("method", {}).get("model")
                    if model:
                        model_record = deepcopy(model)
                        model_record["device"] = (
                            "cpu"
                            if "cpu" in str(model_record.get("runtime", "")).casefold()
                            else "unspecified"
                        )
                        manifest["models"].append(model_record)
                if stage_name == "confidence_and_validation":
                    manifest["quality_gates"] = stage_output.get("quality_gates", [])
                    manifest["validation_summary"] = stage_output.get(
                        "validation_summary"
                    )
                if stage_output.get("fallback_used"):
                    manifest["fallback_events"].append(
                        stage_output.get("fallback")
                        or {
                            "stage": stage_name,
                            "trigger": "Stage reported fallback_used without structured fallback details.",
                        }
                    )
                _write_event(
                    log_path,
                    {"timestamp": record["finished_at"], "event": "stage_completed", **record},
                )
                stage_progress.set_postfix_str(str(record["status"]))
                stage_progress.update(1)

        summary_output = _read_json(outputs["summary_structure"])
        note_output = _read_json(outputs["note_extraction"])
        baseline_output = _read_json(outputs["relation_matching_baseline"])
        semantic_output = _read_json(outputs["relation_matching_semantic"])
        validation_output = _read_json(outputs["confidence_and_validation"])
        final_output = build_final_output(
            config,
            summary_output,
            note_output,
            baseline_output,
            semantic_output,
            validation_output,
            delivery_manifest_path,
        )
        config.output_path.parent.mkdir(parents=True, exist_ok=True)
        config.output_path.write_text(
            json.dumps(final_output, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        manifest["final_output"] = {
            "path": str(config.output_path),
            "sha256": sha256_file(config.output_path),
            "status": final_output["status"],
        }
        manifest["status"] = final_output["status"]
        _write_event(
            log_path,
            {
                "timestamp": _utc_now(),
                "event": "run_completed",
                "status": final_output["status"],
                "output": str(config.output_path),
            },
        )
    except Exception as exc:
        manifest["status"] = "failed"
        manifest["error"] = {
            "type": type(exc).__name__,
            "message": str(exc),
        }
        _write_event(
            log_path,
            {
                "timestamp": _utc_now(),
                "event": "run_failed",
                "error": manifest["error"],
            },
        )
        raise
    finally:
        manifest["finished_at"] = _utc_now()
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        delivery_manifest_path.parent.mkdir(parents=True, exist_ok=True)
        delivery_manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if log_path.exists():
            shutil.copyfile(log_path, delivery_log_path)
    return config.output_path, delivery_manifest_path
