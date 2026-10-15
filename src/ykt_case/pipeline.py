# Bu dosya, her işleme aşamasını bağımsız ve yeniden kullanılabilir çalışma fonksiyonları olarak sunmak için kullanılır.
"""Small, explicit orchestration functions for pipeline stages."""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import statistics
from typing import Any

from ykt_case.config import PipelineConfig
from ykt_case.matching import match_relations_baseline
from ykt_case.note_locator import extract_heading_candidates, locate_target_notes
from ykt_case.note_tables import extract_note_document
from ykt_case.ocr import page_number_from_rendered_image, run_tesseract
from ykt_case.progress import progress_message, track
from ykt_case.semantic_matching import (
    FastEmbedTextEncoder,
    SemanticModelError,
    match_relations_semantic,
    semantic_fallback_output,
)
from ykt_case.rendering import (
    render_pdf_document,
    render_pdf_page_numbers,
    render_pdf_pages,
)
from ykt_case.summary_tables import extract_summary_document
from ykt_case.validation import validate_pipeline_outputs


def _confidence_summary(confidences: list[float]) -> dict[str, float | None]:
    if not confidences:
        return {"mean": None, "p10": None}
    ordered = sorted(confidences)
    p10_index = max(0, int((len(ordered) - 1) * 0.10))
    return {
        "mean": round(statistics.fmean(ordered), 6),
        "p10": round(ordered[p10_index], 6),
    }


def run_summary_ocr(config: PipelineConfig) -> Path:
    render_dir = config.work_dir / "rendered" / "summary"
    ocr_dir = config.work_dir / "ocr"
    progress_message("Özet tablo sayfaları görüntüye dönüştürülüyor...")
    images = render_pdf_pages(
        source_pdf=config.source_pdf,
        pages=config.summary_pages,
        output_dir=render_dir,
        dpi=config.render_dpi,
    )

    pages: list[dict] = []
    for image in track(
        images,
        description="Özet tablo OCR",
        total=len(images),
        unit="sayfa",
    ):
        page_number = page_number_from_rendered_image(image)
        tokens = run_tesseract(
            image,
            language=config.ocr_language,
            page_segmentation_mode=config.ocr_page_segmentation_mode,
        )
        if not tokens:
            raise RuntimeError(
                f"OCR returned no word tokens for configured PDF page {page_number}"
            )
        pages.append(
            {
                "pdf_page_number": page_number,
                "image_path": str(image),
                "token_count": len(tokens),
                "ocr_confidence": _confidence_summary(
                    [token.confidence for token in tokens]
                ),
                "tokens": [asdict(token) for token in tokens],
            }
        )

    output = {
        "stage": "summary_ocr",
        "status": "completed",
        "configured_pages": {
            "start": config.summary_pages.start,
            "end": config.summary_pages.end,
        },
        "ocr": {
            "engine": config.ocr_engine,
            "language": config.ocr_language,
            "page_segmentation_mode": config.ocr_page_segmentation_mode,
            "render_dpi": config.render_dpi,
        },
        "pages": pages,
    }
    ocr_dir.mkdir(parents=True, exist_ok=True)
    output_path = ocr_dir / "summary_ocr.json"
    output_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path


def run_summary_structure(config: PipelineConfig) -> Path:
    """Convert the inspectable OCR artifact into structured summary tables."""

    ocr_path = config.work_dir / "ocr" / "summary_ocr.json"
    if not ocr_path.is_file():
        raise FileNotFoundError(
            f"summary OCR artifact not found: {ocr_path}; run the summary-ocr stage first"
        )
    ocr_output = json.loads(ocr_path.read_text(encoding="utf-8"))
    expected_pages = set(range(config.summary_pages.start, config.summary_pages.end + 1))
    actual_pages = {int(page["pdf_page_number"]) for page in ocr_output.get("pages", [])}
    if actual_pages != expected_pages:
        raise ValueError(
            "OCR artifact pages do not match configured summary range: "
            f"expected={sorted(expected_pages)}, actual={sorted(actual_pages)}"
        )

    result = extract_summary_document(ocr_output)
    output_dir = config.work_dir / "structured"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "summary_tables.json"
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path


def run_note_location(config: PipelineConfig) -> Path:
    """Scan the complete document and locate every configured note."""

    render_dir = config.work_dir / "rendered" / "note_scan"
    progress_message("Doküman dipnot taraması için düşük çözünürlükte hazırlanıyor...")
    images = render_pdf_document(
        source_pdf=config.source_pdf,
        output_dir=render_dir,
        dpi=config.note_search_render_dpi,
    )
    all_candidates = []
    page_summaries: list[dict] = []
    for image in track(
        images,
        description="Dipnot taraması OCR",
        total=len(images),
        unit="sayfa",
    ):
        tokens = run_tesseract(
            image,
            language=config.ocr_language,
            page_segmentation_mode=config.note_search_page_segmentation_mode,
        )
        candidates = extract_heading_candidates(tokens)
        all_candidates.extend(candidates)
        page_summaries.append(
            {
                "pdf_page_number": page_number_from_rendered_image(image),
                "token_count": len(tokens),
                "heading_candidates": [asdict(candidate) for candidate in candidates],
            }
        )
    locations = locate_target_notes(all_candidates, config.target_notes)
    result = {
        "stage": "note_location",
        "status": "completed",
        "scan": {
            "pages_scanned": len(images),
            "render_dpi": config.note_search_render_dpi,
            "ocr_engine": config.ocr_engine,
            "ocr_language": config.ocr_language,
            "page_segmentation_mode": config.note_search_page_segmentation_mode,
        },
        "configured_notes": list(config.target_notes),
        "locations": locations,
        "pages": page_summaries,
    }
    output_dir = config.work_dir / "notes"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "note_locations.json"
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return output_path


def run_note_extraction(config: PipelineConfig) -> Path:
    """Render, OCR, and structure every page found by the note locator."""

    locations_path = config.work_dir / "notes" / "note_locations.json"
    if not locations_path.is_file():
        raise FileNotFoundError(
            f"note locations artifact not found: {locations_path}; run note-locate first"
        )
    location_output = json.loads(locations_path.read_text(encoding="utf-8"))
    configured = sorted(config.target_notes)
    located = sorted(int(location["note_number"]) for location in location_output.get("locations", []))
    if configured != located:
        raise ValueError(
            "note-location artifact does not match configured targets: "
            f"expected={configured}, actual={located}"
        )
    page_numbers = sorted(
        {
            int(page_number)
            for location in location_output["locations"]
            for page_number in location["pdf_pages"]
        }
    )
    render_dir = config.work_dir / "rendered" / "note_extraction"
    progress_message("Bulunan dipnot sayfaları yüksek çözünürlükte hazırlanıyor...")
    images = render_pdf_page_numbers(
        source_pdf=config.source_pdf,
        page_numbers=page_numbers,
        output_dir=render_dir,
        dpi=config.note_extraction_render_dpi,
    )
    pages: list[dict[str, Any]] = []
    for image in track(
        images,
        description="Dipnot tablo OCR",
        total=len(images),
        unit="sayfa",
    ):
        page_number = page_number_from_rendered_image(image)
        tokens = run_tesseract(
            image,
            language=config.ocr_language,
            page_segmentation_mode=config.note_extraction_page_segmentation_mode,
        )
        if not tokens:
            raise RuntimeError(f"OCR returned no tokens for located note page {page_number}")
        pages.append(
            {
                "pdf_page_number": page_number,
                "image_path": str(image),
                "token_count": len(tokens),
                "ocr_confidence": _confidence_summary(
                    [token.confidence for token in tokens]
                ),
                "tokens": [asdict(token) for token in tokens],
            }
        )
    ocr_output = {
        "stage": "note_ocr",
        "status": "completed",
        "ocr": {
            "engine": config.ocr_engine,
            "language": config.ocr_language,
            "page_segmentation_mode": config.note_extraction_page_segmentation_mode,
            "render_dpi": config.note_extraction_render_dpi,
        },
        "pages": pages,
    }
    ocr_dir = config.work_dir / "ocr"
    ocr_dir.mkdir(parents=True, exist_ok=True)
    ocr_path = ocr_dir / "note_ocr.json"
    ocr_path.write_text(
        json.dumps(ocr_output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    result = extract_note_document(ocr_output, location_output["locations"])
    output_dir = config.work_dir / "structured"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "note_tables.json"
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return output_path


def run_baseline_matching(config: PipelineConfig) -> Path:
    """Match configured summary rows to note rows with an explainable baseline."""

    summary_path = config.work_dir / "structured" / "summary_tables.json"
    note_path = config.work_dir / "structured" / "note_tables.json"
    if not summary_path.is_file():
        raise FileNotFoundError(
            f"structured summary artifact not found: {summary_path}; run summary-structure first"
        )
    if not note_path.is_file():
        raise FileNotFoundError(
            f"structured note artifact not found: {note_path}; run note-extract first"
        )
    summary_output = json.loads(summary_path.read_text(encoding="utf-8"))
    note_output = json.loads(note_path.read_text(encoding="utf-8"))
    result = match_relations_baseline(
        summary_output=summary_output,
        note_output=note_output,
        target_notes=config.target_notes,
        top_k=config.matching_top_k,
        minimum_candidate_score=config.matching_minimum_candidate_score,
    )
    output_dir = config.work_dir / "matching"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "baseline_relations.json"
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return output_path


def run_semantic_matching(config: PipelineConfig) -> Path:
    """Run local multilingual embeddings and explicitly fall back if unavailable."""

    summary_path = config.work_dir / "structured" / "summary_tables.json"
    note_path = config.work_dir / "structured" / "note_tables.json"
    if not summary_path.is_file():
        raise FileNotFoundError(
            f"structured summary artifact not found: {summary_path}; run summary-structure first"
        )
    if not note_path.is_file():
        raise FileNotFoundError(
            f"structured note artifact not found: {note_path}; run note-extract first"
        )
    summary_output = json.loads(summary_path.read_text(encoding="utf-8"))
    note_output = json.loads(note_path.read_text(encoding="utf-8"))
    try:
        progress_message("Embedding modeli yükleniyor ve adaylar kodlanıyor...")
        encoder = FastEmbedTextEncoder(
            model_name=config.semantic_model_name,
            cache_dir=str(config.semantic_cache_dir),
            threads=config.semantic_threads,
            allow_download=config.semantic_allow_download,
        )
        result = match_relations_semantic(
            summary_output=summary_output,
            note_output=note_output,
            target_notes=config.target_notes,
            top_k=config.matching_top_k,
            minimum_candidate_score=config.matching_minimum_candidate_score,
            encoder=encoder,
        )
        progress_message("Embedding eşleştirmesi tamamlandı.")
    except SemanticModelError as error:
        progress_message("Embedding kullanılamadı; kayıtlı baseline fallback çalıştırılıyor.")
        baseline_path = run_baseline_matching(config)
        baseline_output = json.loads(baseline_path.read_text(encoding="utf-8"))
        result = semantic_fallback_output(
            baseline_output, config.semantic_model_name, error
        )
    output_dir = config.work_dir / "matching"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "semantic_relations.json"
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return output_path


def run_validation(config: PipelineConfig) -> Path:
    """Validate inspectable artifacts and aggregate final relation confidence."""

    required_paths = {
        "summary_ocr": config.work_dir / "ocr" / "summary_ocr.json",
        "summary_output": config.work_dir / "structured" / "summary_tables.json",
        "note_location": config.work_dir / "notes" / "note_locations.json",
        "note_output": config.work_dir / "structured" / "note_tables.json",
        "baseline_output": config.work_dir / "matching" / "baseline_relations.json",
        "relation_output": config.work_dir / "matching" / "semantic_relations.json",
    }
    missing = [str(path) for path in required_paths.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "validation requires prior pipeline artifacts; missing: " + ", ".join(missing)
        )
    artifacts = {
        name: json.loads(path.read_text(encoding="utf-8"))
        for name, path in required_paths.items()
    }
    result = validate_pipeline_outputs(config=config, **artifacts)
    output_dir = config.work_dir / "validation"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "validation_report.json"
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return output_path
