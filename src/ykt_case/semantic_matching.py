# Bu dosya, çok dilli embedding modeli ve sayısal-yapısal kanıtlarla anlamsal ilişki eşleme yapmak için kullanılır.
"""Multilingual embedding relation matching with explicit model provenance."""

from __future__ import annotations

from copy import deepcopy
from importlib.metadata import version
import math
from pathlib import Path
import statistics
from typing import Any, Protocol, Sequence

from ykt_case.matching import (
    _candidate,
    _referenced_target_notes,
    _select_covering_candidates,
    _summary_values,
)


class SemanticModelError(RuntimeError):
    """Raised only when the optional semantic model cannot load or infer."""


class TextEncoder(Protocol):
    """Minimal interface that keeps relation logic independent of FastEmbed."""

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        ...

    def metadata(self) -> dict[str, Any]:
        ...


class FastEmbedTextEncoder:
    """CPU-friendly ONNX adapter; import remains optional for baseline-only runs."""

    def __init__(
        self,
        model_name: str,
        model_revision: str | None,
        cache_dir: str,
        threads: int,
        allow_download: bool,
    ) -> None:
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:
            raise SemanticModelError(
                "fastembed is not installed; install the semantic extra"
            ) from exc
        try:
            supported = {
                item["model"]: item for item in TextEmbedding.list_supported_models()
            }
            if model_name not in supported:
                raise SemanticModelError(
                    f"semantic model is not supported by FastEmbed: {model_name}"
                )
            self._description = supported[model_name]
            self._model = TextEmbedding(
                model_name=model_name,
                cache_dir=cache_dir,
                threads=threads,
                local_files_only=not allow_download,
                **({"revision": model_revision} if model_revision else {}),
            )
        except SemanticModelError:
            raise
        except Exception as exc:
            raise SemanticModelError(
                f"semantic model could not be loaded: {type(exc).__name__}: {exc}"
            ) from exc
        self._model_name = model_name
        self._model_revision = model_revision
        self._cache_dir = cache_dir
        self._threads = threads
        self._allow_download = allow_download

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        try:
            vectors = [vector.tolist() for vector in self._model.embed(list(texts))]
        except Exception as exc:
            raise SemanticModelError(
                f"semantic inference failed: {type(exc).__name__}: {exc}"
            ) from exc
        return [[float(value) for value in vector] for vector in vectors]

    def metadata(self) -> dict[str, Any]:
        source_repository = self._description.get("sources", {}).get("hf")
        source_revision = self._model_revision
        if source_repository:
            snapshot_root = (
                Path(self._cache_dir)
                / f"models--{source_repository.replace('/', '--')}"
                / "snapshots"
            )
            snapshots = sorted(
                path.name for path in snapshot_root.glob("*") if path.is_dir()
            )
            if source_revision is None and len(snapshots) == 1:
                source_revision = snapshots[0]
        return {
            "provider": "fastembed",
            "provider_version": version("fastembed"),
            "model_name": self._model_name,
            "configured_revision": self._model_revision,
            "runtime": "onnxruntime_cpu",
            "embedding_dimension": self._description.get("dim"),
            "license": self._description.get("license"),
            "declared_size_gb": self._description.get("size_in_GB"),
            "model_sources": self._description.get("sources"),
            "source_revision": source_revision,
            "cache_dir": self._cache_dir,
            "threads": self._threads,
            "download_allowed": self._allow_download,
        }


def build_summary_context(row: dict[str, Any], note_number: int) -> str:
    """Build model text without injecting expected answers or financial values."""

    periods = [
        str(cell["period"])
        for cell in row.get("cells", [])
        if cell.get("role") == "data_cell" and cell.get("period") is not None
    ]
    return " | ".join(
        [
            f"finansal tablo kalemi: {row.get('label') or 'etiketsiz satır'}",
            f"satır türü: {row.get('row_type') or 'bilinmiyor'}",
            f"hedef dipnot: {note_number}",
            f"raporlama dönemleri: {', '.join(periods) or 'bilinmiyor'}",
        ]
    )


def build_note_context(
    table: dict[str, Any], row: dict[str, Any], note_number: int
) -> str:
    """Describe note-row semantics while numeric equality stays a separate feature."""

    headers = [
        str(column.get("normalized_text") or column["raw_text"])
        for column in table.get("columns", [])
        if column.get("raw_text")
    ]
    return " | ".join(
        [
            f"dipnot: {note_number}",
            f"dipnot satırı: {row.get('label') or 'etiketsiz toplam satırı'}",
            f"satır türü: {row.get('row_type') or 'bilinmiyor'}",
            f"tablo sütunları: {', '.join(headers) or 'bilinmiyor'}",
        ]
    )


def _cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("semantic vectors must have the same non-zero dimension")
    left_norm = math.sqrt(math.fsum(value * value for value in left))
    right_norm = math.sqrt(math.fsum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        raise ValueError("semantic model returned a zero vector")
    similarity = math.fsum(a * b for a, b in zip(left, right)) / (
        left_norm * right_norm
    )
    return round(min(1.0, max(0.0, similarity)), 6)


def _encode_unique(
    encoder: TextEncoder, texts: Sequence[str]
) -> dict[str, list[float]]:
    unique_texts = list(dict.fromkeys(texts))
    vectors = encoder.encode(unique_texts)
    if len(vectors) != len(unique_texts):
        raise ValueError("semantic model returned an unexpected vector count")
    return dict(zip(unique_texts, vectors))


def match_relations_semantic(
    summary_output: dict[str, Any],
    note_output: dict[str, Any],
    target_notes: tuple[int, ...],
    top_k: int,
    minimum_candidate_score: float,
    encoder: TextEncoder,
) -> dict[str, Any]:
    """Rank every same-note candidate with semantic, numeric and structural evidence."""

    notes_by_number = {
        int(note["note_number"]): note for note in note_output.get("notes", [])
    }
    relation_inputs: list[dict[str, Any]] = []
    all_contexts: list[str] = []
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
                summary_values = _summary_values(summary_row)
                if not summary_values:
                    raise ValueError(
                        f"summary row {summary_table['table_id']}:{summary_row['row_index']} "
                        "has no valid numeric values for relation matching"
                    )
                summary_context = build_summary_context(summary_row, note_number)
                candidate_inputs = []
                for note_table in note.get("tables", []):
                    for note_row in note_table.get("rows", []):
                        note_context = build_note_context(note_table, note_row, note_number)
                        candidate_inputs.append((note_table, note_row, note_context))
                        all_contexts.append(note_context)
                all_contexts.append(summary_context)
                relation_inputs.append(
                    {
                        "summary_table": summary_table,
                        "summary_row": summary_row,
                        "summary_values": summary_values,
                        "summary_context": summary_context,
                        "note_number": note_number,
                        "candidate_inputs": candidate_inputs,
                    }
                )
    if not relation_inputs:
        raise ValueError("no summary rows reference the configured target notes")

    vectors = _encode_unique(encoder, all_contexts)
    relations: list[dict[str, Any]] = []
    for item in relation_inputs:
        candidates = []
        for note_table, note_row, note_context in item["candidate_inputs"]:
            candidate = _candidate(
                item["summary_table"], item["summary_row"], note_table, note_row
            )
            semantic = _cosine_similarity(
                vectors[item["summary_context"]], vectors[note_context]
            )
            features = candidate["features"]
            candidate["baseline_score"] = candidate["score"]
            candidate["features"]["semantic_similarity"] = semantic
            candidate["features"]["semantic_context"] = {
                "summary": item["summary_context"],
                "note": note_context,
            }
            candidate["score"] = round(
                0.50 * features["numeric_coverage"]
                + 0.25 * semantic
                + 0.10 * features["structural_compatibility"]
                + 0.15 * features["evidence_quality"],
                6,
            )
            candidates.append(candidate)
        candidates.sort(key=lambda candidate: candidate["score"], reverse=True)
        selected, uncovered = _select_covering_candidates(
            candidates,
            summary_value_count=len(item["summary_values"]),
            minimum_score=minimum_candidate_score,
        )
        coverage = 1.0 - len(uncovered) / len(item["summary_values"])
        selected_mean = (
            statistics.fmean(candidate["score"] for candidate in selected)
            if selected
            else 0.0
        )
        confidence = (
            round(0.70 * selected_mean + 0.30 * coverage, 6) if selected else 0.0
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
        summary_table = item["summary_table"]
        summary_row = item["summary_row"]
        summary_row_id = str(
            summary_row.get("row_id")
            or f"{summary_table['table_id']}:row-{summary_row['row_index']}"
        )
        relations.append(
            {
                "relation_id": (
                    f"semantic:{summary_row_id}:note-{item['note_number']}"
                ),
                "method": "multilingual_embedding_numeric_structural",
                "summary_row_id": summary_row_id,
                "summary_table_id": summary_table["table_id"],
                "summary_page_number": int(
                    summary_table["page"]["pdf_page_number"]
                ),
                "summary_row_index": int(summary_row["row_index"]),
                "summary_label": summary_row.get("label"),
                "note_number": item["note_number"],
                "status": status,
                "selected_note_row_ids": [
                    candidate["note_row_id"] for candidate in selected
                ],
                "matched_value_coverage": round(coverage, 6),
                "unmatched_periods": [
                    item["summary_values"][index]["period"]
                    for index in sorted(uncovered)
                ],
                "ambiguous": len(numeric_alternatives) > len(selected),
                "confidence": confidence,
                "top_candidates": candidates[:top_k],
            }
        )
    statuses = {relation["status"] for relation in relations}
    overall_status = (
        "completed"
        if statuses == {"matched"}
        else "completed_with_warnings"
        if "matched" in statuses or "partial_match" in statuses
        else "failed"
    )
    return {
        "stage": "relation_matching_semantic",
        "status": overall_status,
        "fallback_used": False,
        "method": {
            "name": "multilingual_embedding_numeric_structural",
            "weights": {
                "numeric_coverage": 0.50,
                "semantic_similarity": 0.25,
                "structural_compatibility": 0.10,
                "evidence_quality": 0.15,
            },
            "minimum_candidate_score": minimum_candidate_score,
            "top_k": top_k,
            "model": encoder.metadata(),
            "input_policy": (
                "labels, row types, note number, periods, and column headers; "
                "financial values are scored separately and expected answers are excluded"
            ),
        },
        "relations": relations,
    }


def semantic_fallback_output(
    baseline_output: dict[str, Any], model_name: str, error: Exception
) -> dict[str, Any]:
    """Return attributable baseline predictions when semantic inference is unavailable."""

    result = deepcopy(baseline_output)
    result["stage"] = "relation_matching_semantic"
    result["status"] = "completed_with_warnings"
    result["fallback_used"] = True
    result["fallback"] = {
        "trigger": "semantic_model_unavailable_or_inference_failed",
        "requested_model": model_name,
        "method_used": "lexical_numeric_structural_baseline",
        "reason": f"{type(error).__name__}: {error}",
        "original_result": {
            "stage": "semantic_inference",
            "status": "failed",
            "error_type": type(error).__name__,
            "error_message": str(error),
        },
        "fallback_result": {
            "stage": baseline_output.get("stage"),
            "status": baseline_output.get("status"),
            "method": baseline_output.get("method"),
            "relation_count": len(baseline_output.get("relations", [])),
        },
        "resulting_quality_change": {
            "semantic_evidence_available": False,
            "prediction_source": "baseline",
            "run_status": "completed_with_warnings",
            "interpretation": (
                "Relations remain available, but semantic evidence and its independent "
                "agreement signal are unavailable."
            ),
        },
    }
    result["method"] = {
        "name": "baseline_fallback_for_semantic",
        "requested_model": model_name,
        "fallback_method": baseline_output.get("method"),
    }
    for relation in result.get("relations", []):
        relation["relation_id"] = relation["relation_id"].replace(
            "baseline:", "semantic-fallback:", 1
        )
        relation["method"] = "baseline_fallback_for_semantic"
    return result
