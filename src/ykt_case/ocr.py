# Bu dosya, Tesseract OCR çıktısını metin, koordinat ve güven bilgisiyle üretmek için kullanılır.
"""Tesseract OCR integration with word-level provenance."""

from __future__ import annotations

import csv
from io import StringIO
from pathlib import Path
import re
import shutil
import subprocess

from ykt_case.schemas import BoundingBox, OcrToken, PageIdentity


def parse_tesseract_tsv(tsv: str, pdf_page_number: int) -> list[OcrToken]:
    page = PageIdentity(pdf_page_number=pdf_page_number, page_index=pdf_page_number - 1)
    tokens: list[OcrToken] = []
    for row in csv.DictReader(StringIO(tsv), delimiter="\t"):
        text = (row.get("text") or "").strip()
        if row.get("level") != "5" or not text:
            continue
        raw_confidence = float(row["conf"])
        if raw_confidence < 0:
            continue
        tokens.append(
            OcrToken(
                text=text,
                bbox=BoundingBox(
                    left=int(row["left"]),
                    top=int(row["top"]),
                    width=int(row["width"]),
                    height=int(row["height"]),
                ),
                confidence=min(raw_confidence / 100.0, 1.0),
                page=page,
                block_number=int(row["block_num"]),
                paragraph_number=int(row["par_num"]),
                line_number=int(row["line_num"]),
                word_number=int(row["word_num"]),
            )
        )
    return tokens


def page_number_from_rendered_image(path: Path) -> int:
    match = re.search(r"-(\d+)\.(?:png|jpe?g)$", path.name, flags=re.IGNORECASE)
    if match is None:
        raise ValueError(f"cannot derive PDF page number from {path.name}")
    return int(match.group(1))


def run_tesseract(
    image_path: Path,
    language: str,
    page_segmentation_mode: int,
) -> list[OcrToken]:
    executable = shutil.which("tesseract")
    if executable is None:
        raise RuntimeError("tesseract is required but was not found on PATH")
    command = [
        executable,
        str(image_path),
        "stdout",
        "-l",
        language,
        "--psm",
        str(page_segmentation_mode),
        "tsv",
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"OCR failed for {image_path.name}: {completed.stderr.strip()}")
    return parse_tesseract_tsv(
        completed.stdout,
        pdf_page_number=page_number_from_rendered_image(image_path),
    )
