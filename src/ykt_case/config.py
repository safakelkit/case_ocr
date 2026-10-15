# Bu dosya, JSON yapılandırmasını yüklemek ve proje kurallarına göre doğrulamak için kullanılır.
"""Configuration loading and validation."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PageRange:
    """Inclusive, one-based PDF page range."""

    start: int
    end: int

    def __post_init__(self) -> None:
        if self.start < 1:
            raise ValueError("summary page start must be one-based and positive")
        if self.end < self.start:
            raise ValueError("summary page end must be greater than or equal to start")


@dataclass(frozen=True)
class QualityGate:
    name: str
    threshold: float
    comparator: str
    action: str
    rationale: str

    def __post_init__(self) -> None:
        if self.comparator not in {"gte", "lte"}:
            raise ValueError(f"quality gate {self.name} comparator must be gte or lte")
        if self.action not in {"stop", "continue_with_warning"}:
            raise ValueError(
                f"quality gate {self.name} action must be stop or continue_with_warning"
            )
        if not self.rationale.strip():
            raise ValueError(f"quality gate {self.name} rationale cannot be empty")


@dataclass(frozen=True)
class PipelineConfig:
    source_pdf: Path
    summary_pages: PageRange
    target_notes: tuple[int, ...]
    output_path: Path
    work_dir: Path
    render_dpi: int
    ocr_engine: str
    ocr_language: str
    ocr_page_segmentation_mode: int
    note_search_render_dpi: int
    note_search_page_segmentation_mode: int
    note_extraction_render_dpi: int
    note_extraction_page_segmentation_mode: int
    matching_top_k: int
    matching_minimum_candidate_score: float
    semantic_model_name: str
    semantic_cache_dir: Path
    semantic_threads: int
    semantic_allow_download: bool
    quality_gates: tuple[QualityGate, ...]
    random_seed: int

    def __post_init__(self) -> None:
        if not self.target_notes:
            raise ValueError("at least one target note is required")
        if any(note < 1 for note in self.target_notes):
            raise ValueError("target note numbers must be positive")
        if len(set(self.target_notes)) != len(self.target_notes):
            raise ValueError("target note numbers must be unique")
        if self.render_dpi < 72:
            raise ValueError("render_dpi must be at least 72")
        if self.ocr_engine != "tesseract":
            raise ValueError("only the tesseract OCR engine is currently supported")
        if not self.ocr_language.strip():
            raise ValueError("ocr language cannot be empty")
        if not 0 <= self.ocr_page_segmentation_mode <= 13:
            raise ValueError("Tesseract page segmentation mode must be between 0 and 13")
        if self.note_search_render_dpi < 72:
            raise ValueError("note search render DPI must be at least 72")
        if not 0 <= self.note_search_page_segmentation_mode <= 13:
            raise ValueError("note search page segmentation mode must be between 0 and 13")
        if self.note_extraction_render_dpi < 72:
            raise ValueError("note extraction render DPI must be at least 72")
        if not 0 <= self.note_extraction_page_segmentation_mode <= 13:
            raise ValueError("note extraction page segmentation mode must be between 0 and 13")
        if self.matching_top_k < 1:
            raise ValueError("matching top_k must be positive")
        if not 0.0 <= self.matching_minimum_candidate_score <= 1.0:
            raise ValueError("matching minimum candidate score must be in [0, 1]")
        if not self.semantic_model_name.strip():
            raise ValueError("semantic model name cannot be empty")
        if self.semantic_threads < 1:
            raise ValueError("semantic threads must be positive")
        names = [gate.name for gate in self.quality_gates]
        if not names:
            raise ValueError("at least one quality gate is required")
        if len(names) != len(set(names)):
            raise ValueError("quality gate names must be unique")
        if self.random_seed < 0:
            raise ValueError("random seed cannot be negative")


def _require_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def load_config(path: str | Path) -> PipelineConfig:
    """Load config without resolving any known answer or note location."""

    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as stream:
        raw = _require_mapping(json.load(stream), "config")

    page_data = _require_mapping(raw.get("summary_pages"), "summary_pages")
    ocr_data = _require_mapping(raw.get("ocr"), "ocr")
    note_search_data = _require_mapping(raw.get("note_search", {}), "note_search")
    note_extraction_data = _require_mapping(
        raw.get("note_extraction", {}), "note_extraction"
    )
    matching_data = _require_mapping(raw.get("matching", {}), "matching")
    semantic_data = _require_mapping(raw.get("semantic", {}), "semantic")
    quality_gate_data = _require_mapping(
        raw.get("quality_gates", {}), "quality_gates"
    )
    notes = raw.get("target_notes")
    if not isinstance(notes, list) or not all(isinstance(note, int) for note in notes):
        raise ValueError("target_notes must be a list of integers")

    return PipelineConfig(
        source_pdf=Path(raw["source_pdf"]),
        summary_pages=PageRange(start=page_data["start"], end=page_data["end"]),
        target_notes=tuple(notes),
        output_path=Path(raw["output_path"]),
        work_dir=Path(raw.get("work_dir", "work")),
        render_dpi=int(raw.get("render_dpi", 300)),
        ocr_engine=str(ocr_data.get("engine", "tesseract")).casefold(),
        ocr_language=str(ocr_data.get("language", "tur+eng")),
        ocr_page_segmentation_mode=int(ocr_data.get("page_segmentation_mode", 3)),
        note_search_render_dpi=int(note_search_data.get("render_dpi", 110)),
        note_search_page_segmentation_mode=int(
            note_search_data.get("page_segmentation_mode", 6)
        ),
        note_extraction_render_dpi=int(
            note_extraction_data.get("render_dpi", raw.get("render_dpi", 300))
        ),
        note_extraction_page_segmentation_mode=int(
            note_extraction_data.get("page_segmentation_mode", 3)
        ),
        matching_top_k=int(matching_data.get("top_k", 5)),
        matching_minimum_candidate_score=float(
            matching_data.get("minimum_candidate_score", 0.35)
        ),
        semantic_model_name=str(
            semantic_data.get(
                "model_name",
                "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
            )
        ),
        semantic_cache_dir=Path(
            semantic_data.get("cache_dir", "work/models/fastembed")
        ),
        semantic_threads=int(semantic_data.get("threads", 4)),
        semantic_allow_download=bool(semantic_data.get("allow_download", True)),
        quality_gates=tuple(
            QualityGate(
                name=name,
                threshold=float(_require_mapping(value, f"quality_gates.{name}")["threshold"]),
                comparator=str(value.get("comparator", "gte")),
                action=str(value.get("action", "continue_with_warning")),
                rationale=str(value.get("rationale", "")),
            )
            for name, value in quality_gate_data.items()
        ),
        random_seed=int(raw.get("random_seed", 0)),
    )