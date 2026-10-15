#!/usr/bin/env python3
# Bu dosya, Tesseract sayfa bölümleme modlarını sabit bir OCR değerlendirme örneği üzerinde karşılaştırmak için kullanılır.
"""Compare Tesseract page-segmentation modes on configured summary pages.

This is an evaluation utility, not part of the runtime extraction logic.
Human-reviewed expectations are loaded from a separate file and are used only
to measure OCR behavior.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import sys
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from ykt_case.config import load_config  # noqa: E402
from ykt_case.ocr import run_tesseract  # noqa: E402
from ykt_case.rendering import render_pdf_pages  # noqa: E402
from ykt_case.schemas import OcrToken  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare Tesseract PSM modes on the same rendered pages"
    )
    parser.add_argument(
        "--config",
        default="configs/default.json",
        help="Pipeline configuration path",
    )
    parser.add_argument(
        "--expectations",
        default="evaluation/psm_expectations.json",
        help="Human-reviewed evaluation expectations",
    )
    parser.add_argument(
        "--psm",
        type=int,
        nargs="+",
        default=[3, 4, 6, 11],
        help="PSM values to compare",
    )
    parser.add_argument(
        "--output-prefix",
        default="work/evaluation/psm_comparison",
        help="Output path without extension; .json and .md are written",
    )
    parser.add_argument(
        "--rerender",
        action="store_true",
        help="Force PDF rendering instead of reusing existing summary-page PNGs",
    )
    return parser.parse_args()


def load_expectations(path: Path) -> dict[int, dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    pages = data.get("pages")
    if not isinstance(pages, dict):
        raise ValueError("expectations must contain a pages object")
    return {int(page): value for page, value in pages.items()}


def existing_rendered_pages(
    render_dir: Path,
    start_page: int,
    end_page: int,
) -> list[Path] | None:
    expected = [
        render_dir / f"summary-page-{page:02d}.png"
        for page in range(start_page, end_page + 1)
    ]
    return expected if all(path.is_file() for path in expected) else None


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, int((len(ordered) - 1) * fraction))
    return ordered[index]


def closest_token(
    tokens: list[OcrToken],
    text: str,
    anchor_y: float | None,
) -> OcrToken | None:
    matches = [token for token in tokens if token.text.casefold() == text.casefold()]
    if not matches:
        return None
    if anchor_y is None:
        return matches[0]
    return min(matches, key=lambda token: abs(token_center_y(token) - anchor_y))


def token_center_y(token: OcrToken) -> float:
    return token.bbox.top + token.bbox.height / 2


def evaluate_target_row(
    tokens: list[OcrToken],
    target_row: dict[str, Any],
) -> dict[str, Any]:
    values = [str(value) for value in target_row.get("values", [])]
    anchor = closest_token(tokens, values[0], None) if values else None
    anchor_y = token_center_y(anchor) if anchor else None

    label_tokens = [str(value) for value in target_row.get("label_tokens", [])]
    numeric_tokens: list[str] = []
    note_reference = target_row.get("note_reference")
    if note_reference is not None:
        numeric_tokens.append(str(note_reference))
    numeric_tokens.extend(values)
    expected = label_tokens + numeric_tokens

    matched = [closest_token(tokens, text, anchor_y) for text in expected]
    found = [token for token in matched if token is not None]
    all_found = len(found) == len(expected)
    y_spread = None
    all_tokens_same_tesseract_line = False
    numeric_cells_same_tesseract_line = False
    if all_found and found:
        centers = [token_center_y(token) for token in found]
        y_spread = round(max(centers) - min(centers), 2)
        line_ids = {
            (token.block_number, token.paragraph_number, token.line_number)
            for token in found
        }
        all_tokens_same_tesseract_line = len(line_ids) == 1
        numeric_start = len(label_tokens)
        numeric_found = found[numeric_start:]
        numeric_line_ids = {
            (token.block_number, token.paragraph_number, token.line_number)
            for token in numeric_found
        }
        numeric_cells_same_tesseract_line = len(numeric_line_ids) == 1

    return {
        "expected": expected,
        "found": [token.text if token is not None else None for token in matched],
        "all_found": all_found,
        "y_spread_px": y_spread,
        "all_tokens_same_tesseract_line": all_tokens_same_tesseract_line,
        "numeric_cells_same_tesseract_line": numeric_cells_same_tesseract_line,
    }


def evaluate_page(
    tokens: list[OcrToken],
    expectation: dict[str, Any],
) -> dict[str, Any]:
    confidences = [token.confidence for token in tokens]
    expected_tokens = [str(value) for value in expectation.get("expected_tokens", [])]
    expected_hits = {
        text: any(token.text.casefold() == text.casefold() for token in tokens)
        for text in expected_tokens
    }
    result: dict[str, Any] = {
        "token_count": len(tokens),
        "mean_confidence": round(statistics.fmean(confidences), 6)
        if confidences
        else None,
        "p10_confidence": round(percentile(confidences, 0.10), 6)
        if confidences
        else None,
        "expected_token_hits": expected_hits,
        "expected_hit_count": sum(expected_hits.values()),
        "expected_token_count": len(expected_hits),
    }
    target_row = expectation.get("target_row")
    if isinstance(target_row, dict):
        result["target_row"] = evaluate_target_row(tokens, target_row)
    return result


def aggregate_mode(pages: list[dict[str, Any]]) -> dict[str, Any]:
    expected_found = sum(page["expected_hit_count"] for page in pages)
    expected_total = sum(page["expected_token_count"] for page in pages)
    target_rows = [page["target_row"] for page in pages if "target_row" in page]
    complete_target_rows = sum(row["all_found"] for row in target_rows)
    clean_target_rows = sum(
        row["numeric_cells_same_tesseract_line"] for row in target_rows
    )
    mean_confidences = [
        page["mean_confidence"]
        for page in pages
        if page["mean_confidence"] is not None
    ]
    return {
        "expected_found": expected_found,
        "expected_total": expected_total,
        "complete_target_rows": complete_target_rows,
        "target_row_count": len(target_rows),
        "clean_target_rows": clean_target_rows,
        "mean_confidence": round(statistics.fmean(mean_confidences), 6)
        if mean_confidences
        else None,
    }


def recommendation_key(mode: dict[str, Any]) -> tuple[int, int, int, float]:
    aggregate = mode["aggregate"]
    return (
        aggregate["expected_found"],
        aggregate["complete_target_rows"],
        aggregate["clean_target_rows"],
        aggregate["mean_confidence"] or 0.0,
    )


def markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# Tesseract PSM Comparison",
        "",
        f"Recommended PSM: **{report['recommended_psm']}**",
        "",
        "The recommendation is selected lexicographically by expected-token hits, "
        "complete target rows, clean Tesseract row grouping, and mean OCR confidence.",
        "",
        "| PSM | Page | Tokens | Mean confidence | P10 | Expected hits | "
        "Target row | Numeric cells same OCR line | Y spread (px) |",
        "|---:|---:|---:|---:|---:|---:|---|---|---:|",
    ]
    for mode in report["modes"]:
        for page in mode["pages"]:
            target = page.get("target_row")
            lines.append(
                "| {psm} | {page} | {tokens} | {mean} | {p10} | {hits} | "
                "{target_found} | {same_line} | {spread} |".format(
                    psm=mode["psm"],
                    page=page["pdf_page_number"],
                    tokens=page["token_count"],
                    mean=page["mean_confidence"],
                    p10=page["p10_confidence"],
                    hits=f"{page['expected_hit_count']}/{page['expected_token_count']}",
                    target_found="-" if target is None else target["all_found"],
                    same_line="-"
                    if target is None
                    else target["numeric_cells_same_tesseract_line"],
                    spread="-" if target is None else target["y_spread_px"],
                )
            )
    lines.extend(
        [
            "",
            "## Aggregate results",
            "",
            "| PSM | Expected hits | Complete target rows | Clean numeric rows | Mean confidence |",
            "|---:|---:|---:|---:|---:|",
        ]
    )
    for mode in report["modes"]:
        aggregate = mode["aggregate"]
        lines.append(
            "| {psm} | {hits}/{total} | {complete}/{rows} | {clean}/{rows} | {mean} |".format(
                psm=mode["psm"],
                hits=aggregate["expected_found"],
                total=aggregate["expected_total"],
                complete=aggregate["complete_target_rows"],
                clean=aggregate["clean_target_rows"],
                rows=aggregate["target_row_count"],
                mean=aggregate["mean_confidence"],
            )
        )
    lines.extend(
        [
            "",
            "> Expectations are human-reviewed evaluation data. They are not passed "
            "to the runtime extraction pipeline.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    config = load_config(REPOSITORY_ROOT / args.config)
    expectations = load_expectations(REPOSITORY_ROOT / args.expectations)
    output_prefix = REPOSITORY_ROOT / args.output_prefix

    render_dir = REPOSITORY_ROOT / config.work_dir / "rendered" / "summary"
    images = None if args.rerender else existing_rendered_pages(
        render_dir,
        config.summary_pages.start,
        config.summary_pages.end,
    )
    render_source = "existing_images"
    if images is None:
        try:
            images = render_pdf_pages(
                source_pdf=REPOSITORY_ROOT / config.source_pdf,
                pages=config.summary_pages,
                output_dir=render_dir,
                dpi=config.render_dpi,
            )
        except RuntimeError as error:
            if "pdftoppm" not in str(error):
                raise
            raise RuntimeError(
                "Rendered page images are missing and pdftoppm is unavailable. "
                "Install Poppler (macOS: `brew install poppler`) or place the "
                "configured pages under work/rendered/summary before retrying."
            ) from error
        render_source = "pdf_render"

    modes: list[dict[str, Any]] = []
    for psm in args.psm:
        pages: list[dict[str, Any]] = []
        for image in images:
            tokens = run_tesseract(
                image,
                language=config.ocr_language,
                page_segmentation_mode=psm,
            )
            pdf_page_number = tokens[0].page.pdf_page_number if tokens else None
            if pdf_page_number is None:
                raise RuntimeError(f"OCR returned no tokens for {image}")
            expectation = expectations.get(pdf_page_number, {})
            result = evaluate_page(tokens, expectation)
            result.update(
                {
                    "pdf_page_number": pdf_page_number,
                    "image_path": str(image.relative_to(REPOSITORY_ROOT)),
                }
            )
            pages.append(result)
        modes.append({"psm": psm, "pages": pages, "aggregate": aggregate_mode(pages)})

    recommended = max(modes, key=recommendation_key)["psm"]
    report = {
        "purpose": "evaluation_only",
        "config": args.config,
        "expectations": args.expectations,
        "compared_psm_modes": args.psm,
        "render_source": render_source,
        "recommended_psm": recommended,
        "selection_order": [
            "expected_token_hits",
            "complete_target_rows",
            "clean_target_rows",
            "mean_confidence",
        ],
        "modes": modes,
    }

    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    json_path = output_prefix.with_suffix(".json")
    markdown_path = output_prefix.with_suffix(".md")
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(markdown_report(report), encoding="utf-8")

    print(f"Recommended PSM: {recommended}")
    print(f"JSON report: {json_path.relative_to(REPOSITORY_ROOT)}")
    print(f"Markdown report: {markdown_path.relative_to(REPOSITORY_ROOT)}")


if __name__ == "__main__":
    main()
