#!/usr/bin/env python3
# Bu dosya, farklı çok dilli embedding modellerini aynı ilişki eşleme koşullarında karşılaştırmak için kullanılır.
"""Compare multilingual embedding models under one fixed relation contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
import statistics
import time
from typing import Any

from ykt_case.config import load_config
from ykt_case.relation_evaluation import evaluate_relation_output
from ykt_case.semantic_matching import FastEmbedTextEncoder, match_relations_semantic


DEFAULT_MODELS = (
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    "minishlab/potion-multilingual-128M",
    "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _cache_size_bytes(cache_dir: Path, source_repository: str | None) -> int | None:
    if not source_repository:
        return None
    root = cache_dir / f"models--{source_repository.replace('/', '--')}"
    if not root.exists():
        return None
    total = 0
    seen: set[tuple[int, int]] = set()
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        stat = path.stat()
        identity = (stat.st_dev, stat.st_ino)
        if identity in seen:
            continue
        seen.add(identity)
        total += stat.st_size
    return total


def _candidate_count(summary: dict[str, Any], notes: dict[str, Any], targets: tuple[int, ...]) -> int:
    note_rows = {
        int(note["note_number"]): sum(
            len(table.get("rows", [])) for table in note.get("tables", [])
        )
        for note in notes.get("notes", [])
    }
    return sum(
        note_rows.get(int(row["note_reference"]), 0)
        for table in summary.get("tables", [])
        for row in table.get("rows", [])
        if str(row.get("note_reference", "")).isdigit()
        and int(row["note_reference"]) in targets
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark multilingual embeddings on the fixed relation candidates"
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--expectations", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--models", nargs="+", default=list(DEFAULT_MODELS))
    parser.add_argument("--warm-runs", type=int, default=3)
    parser.add_argument("--allow-download", action="store_true")
    args = parser.parse_args()
    if args.warm_runs < 1:
        raise ValueError("warm-runs must be positive")

    config = load_config(args.config)
    summary = _read_json(config.work_dir / "structured" / "summary_tables.json")
    notes = _read_json(config.work_dir / "structured" / "note_tables.json")
    expectations = _read_json(args.expectations)
    candidate_count = _candidate_count(summary, notes, config.target_notes)
    results: list[dict[str, Any]] = []

    for model_name in args.models:
        started = time.perf_counter()
        try:
            encoder = FastEmbedTextEncoder(
                model_name=model_name,
                cache_dir=str(config.semantic_cache_dir),
                threads=config.semantic_threads,
                allow_download=args.allow_download,
            )
            load_seconds = time.perf_counter() - started
            first_started = time.perf_counter()
            prediction = match_relations_semantic(
                summary_output=summary,
                note_output=notes,
                target_notes=config.target_notes,
                top_k=config.matching_top_k,
                minimum_candidate_score=config.matching_minimum_candidate_score,
                encoder=encoder,
            )
            first_inference_seconds = time.perf_counter() - first_started
            warm_times = []
            for _ in range(args.warm_runs):
                warm_started = time.perf_counter()
                match_relations_semantic(
                    summary_output=summary,
                    note_output=notes,
                    target_notes=config.target_notes,
                    top_k=config.matching_top_k,
                    minimum_candidate_score=config.matching_minimum_candidate_score,
                    encoder=encoder,
                )
                warm_times.append(time.perf_counter() - warm_started)
            evaluation = evaluate_relation_output(prediction, expectations)
            metadata = encoder.metadata()
            source_repository = metadata.get("model_sources", {}).get("hf")
            results.append(
                {
                    "status": "completed",
                    "model": metadata,
                    "candidate_count": candidate_count,
                    "timing_seconds": {
                        "initialization": round(load_seconds, 6),
                        "initialization_may_include_download": args.allow_download,
                        "first_inference": round(first_inference_seconds, 6),
                        "warm_runs": [round(value, 6) for value in warm_times],
                        "warm_median": round(statistics.median(warm_times), 6),
                    },
                    "cache_size_bytes": _cache_size_bytes(
                        config.semantic_cache_dir, source_repository
                    ),
                    "evaluation": evaluation,
                    "ranking": [
                        {
                            "summary_row_id": relation["summary_row_id"],
                            "selected_note_row_ids": relation[
                                "selected_note_row_ids"
                            ],
                            "confidence": relation["confidence"],
                            "ranked_note_row_ids": [
                                candidate["note_row_id"]
                                for candidate in relation["top_candidates"]
                            ],
                            "semantic_scores": [
                                candidate["features"]["semantic_similarity"]
                                for candidate in relation["top_candidates"]
                            ],
                        }
                        for relation in prediction["relations"]
                    ],
                }
            )
        except Exception as error:
            results.append(
                {
                    "status": "failed",
                    "model_name": model_name,
                    "error": f"{type(error).__name__}: {error}",
                }
            )

    completed = [item for item in results if item["status"] == "completed"]
    report = {
        "stage": "embedding_model_benchmark",
        "status": "completed" if len(completed) == len(results) else "completed_with_warnings",
        "methodology": {
            "candidate_count": candidate_count,
            "reviewed_relation_count": len(expectations.get("examples", [])),
            "fixed_controls": [
                "structured summary and note artifacts",
                "candidate set and context construction",
                "numeric, structural, and extraction weights",
                "top-k and minimum candidate threshold",
                "CPU thread count and evaluator",
            ],
            "changed_variable": "embedding model only",
            "warm_run_count": args.warm_runs,
            "download_allowed": args.allow_download,
            "device": "cpu",
            "platform": platform.platform(),
            "interpretation_limit": (
                "Two reviewed relations cannot support a general model-quality claim; "
                "ranking changes, resource cost, and operational behavior are diagnostic."
            ),
        },
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "completed_models": len(completed),
                "output": str(args.output),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
