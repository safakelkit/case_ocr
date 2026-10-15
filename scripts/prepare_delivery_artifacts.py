#!/usr/bin/env python3
# Bu dosya, doğrulanmış değerlendirme raporlarını sabit teslim yollarına kopyalayıp kapsam-kanıt indeksini üretmek için kullanılır.
"""Prepare stable, repository-visible evidence artifacts for delivery."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil


EVALUATION_FILES = (
    "baseline_relation_evaluation.json",
    "semantic_relation_evaluation.json",
    "relation_method_comparison.json",
    "embedding_model_benchmark.json",
    "psm_comparison.json",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def prepare_delivery(project_root: Path) -> Path:
    outputs = project_root / "outputs"
    evaluation_source = project_root / "work" / "evaluation"
    evaluation_target = outputs / "evaluation"
    required_runtime = (
        outputs / "result.json",
        outputs / "run_manifest.json",
        outputs / "run_events.jsonl",
    )
    missing_runtime = [path for path in required_runtime if not path.is_file()]
    missing_evaluation = [
        evaluation_source / name
        for name in EVALUATION_FILES
        if not (evaluation_source / name).is_file()
    ]
    missing = [*missing_runtime, *missing_evaluation]
    if missing:
        joined = "\n".join(f"- {path}" for path in missing)
        raise FileNotFoundError(f"Teslim için gerekli artefaktlar eksik:\n{joined}")

    evaluation_target.mkdir(parents=True, exist_ok=True)
    for name in EVALUATION_FILES:
        shutil.copyfile(evaluation_source / name, evaluation_target / name)

    delivered_paths = [
        *required_runtime,
        *(evaluation_target / name for name in EVALUATION_FILES),
    ]
    index = {
        "schema_version": "1.0",
        "purpose": "Case kapsamı ile teslim artefaktları arasındaki sabit kanıt indeksi.",
        "runtime_artifacts": {
            "final_result": "outputs/result.json",
            "run_manifest": "outputs/run_manifest.json",
            "event_log": "outputs/run_events.jsonl",
        },
        "evaluation_artifacts": {
            "baseline_metrics": "outputs/evaluation/baseline_relation_evaluation.json",
            "semantic_metrics": "outputs/evaluation/semantic_relation_evaluation.json",
            "method_comparison": "outputs/evaluation/relation_method_comparison.json",
            "embedding_benchmark": "outputs/evaluation/embedding_model_benchmark.json",
            "ocr_psm_comparison": "outputs/evaluation/psm_comparison.json",
        },
        "artifact_inventory": [
            {
                "path": str(path.relative_to(project_root)),
                "size_bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
            for path in delivered_paths
        ],
        "requirement_evidence": [
            {
                "requirement": "Özet finansal tablolar, başlıklar, satırlar ve sütunlar",
                "artifact": "outputs/result.json",
                "json_pointer": "/summary_tables",
            },
            {
                "requirement": "Şirket, dönem ve para birimi metadatası ile kaynak kanıtı",
                "artifact": "outputs/result.json",
                "json_pointer": "/document",
            },
            {
                "requirement": "Ham ve normalize hücre değerleri; tire, boş ve sıfır ayrımı",
                "artifact": "outputs/result.json",
                "json_pointer": "/summary_tables/*/rows/*/cells",
            },
            {
                "requirement": "Ana, alt, bölüm, ara toplam ve toplam ilişkileri",
                "artifact": "outputs/result.json",
                "json_pointer": "/summary_tables/*/rows",
            },
            {
                "requirement": "Yapılandırılan dipnotun otomatik konumu ve tabloları",
                "artifact": "outputs/result.json",
                "json_pointer": "/notes",
            },
            {
                "requirement": "Özet satırı ile dipnot satırı ilişkileri",
                "artifact": "outputs/result.json",
                "json_pointer": "/matching/relations",
            },
            {
                "requirement": "Tablo, satır, hücre ve ilişki güvenleri ile inceleme bayrakları",
                "artifact": "outputs/result.json",
                "json_pointer": "/review_policy",
            },
            {
                "requirement": "Kalite kapıları ve yapısal, biçimsel, finansal doğrulamalar",
                "artifact": "outputs/result.json",
                "json_pointer": "/validation",
            },
            {
                "requirement": "İki ilişki eşleme yaklaşımının örnek bazlı karşılaştırması",
                "artifact": "outputs/evaluation/relation_method_comparison.json",
                "json_pointer": "/examples",
            },
            {
                "requirement": "Model, bağımlılık, checksum, aşama ve fallback çalışma kaydı",
                "artifact": "outputs/run_manifest.json",
                "json_pointer": "/",
            },
        ],
    }
    index_path = outputs / "delivery_index.json"
    index_path.write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return index_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    index_path = prepare_delivery(args.project_root.resolve())
    print(json.dumps({"status": "completed", "output": str(index_path)}, indent=2))


if __name__ == "__main__":
    main()
