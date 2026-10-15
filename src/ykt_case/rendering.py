# Bu dosya, yapılandırılmış PDF sayfalarını Poppler aracılığıyla kontrollü çözünürlükte görüntüye dönüştürmek için kullanılır.
"""PDF page rendering through the Poppler command-line interface."""

from __future__ import annotations

from pathlib import Path
import re
import shutil
import subprocess

from ykt_case.config import PageRange


def build_render_command(
    executable: str,
    source_pdf: Path,
    output_prefix: Path,
    pages: PageRange,
    dpi: int,
) -> list[str]:
    return [
        executable,
        "-f",
        str(pages.start),
        "-l",
        str(pages.end),
        "-png",
        "-r",
        str(dpi),
        str(source_pdf),
        str(output_prefix),
    ]


def _page_number(path: Path) -> int:
    match = re.search(r"-(\d+)\.(?:png|jpe?g)$", path.name, flags=re.IGNORECASE)
    if match is None:
        raise ValueError(f"cannot derive PDF page number from {path.name}")
    return int(match.group(1))


def select_configured_pages(rendered: list[Path], pages: PageRange) -> list[Path]:
    """Return only the configured pages, ignoring stale renders from older runs."""

    by_page = {_page_number(path): path for path in rendered}
    expected = set(range(pages.start, pages.end + 1))
    missing = expected.difference(by_page)
    if missing:
        raise RuntimeError(
            f"rendered pages are missing from configured range: {sorted(missing)}"
        )
    return [by_page[page] for page in sorted(expected)]


def render_pdf_pages(
    source_pdf: Path,
    pages: PageRange,
    output_dir: Path,
    dpi: int,
) -> list[Path]:
    if not source_pdf.is_file():
        raise FileNotFoundError(f"source PDF not found: {source_pdf}")

    executable = shutil.which("pdftoppm")
    if executable is None:
        raise RuntimeError("pdftoppm is required but was not found on PATH")

    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = output_dir / "summary-page"
    command = build_render_command(executable, source_pdf, prefix, pages, dpi)
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"PDF rendering failed: {completed.stderr.strip()}")

    rendered = list(output_dir.glob("summary-page-*.png"))
    return select_configured_pages(rendered, pages)


def render_pdf_document(
    source_pdf: Path,
    output_dir: Path,
    dpi: int,
) -> list[Path]:
    """Render every PDF page as a lightweight JPEG for document-wide scanning."""

    if not source_pdf.is_file():
        raise FileNotFoundError(f"source PDF not found: {source_pdf}")
    executable = shutil.which("pdftoppm")
    if executable is None:
        raise RuntimeError("pdftoppm is required but was not found on PATH")

    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = output_dir / "note-scan-page"
    command = [
        executable,
        "-jpeg",
        "-jpegopt",
        "quality=80",
        "-r",
        str(dpi),
        str(source_pdf),
        str(prefix),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"document rendering failed: {completed.stderr.strip()}")
    rendered = sorted(output_dir.glob("note-scan-page-*.jpg"), key=_page_number)
    if not rendered:
        raise RuntimeError("document rendering produced no page images")
    return rendered


def render_pdf_page_numbers(
    source_pdf: Path,
    page_numbers: list[int],
    output_dir: Path,
    dpi: int,
) -> list[Path]:
    """Render an explicit set of one-based PDF pages without assuming contiguity."""

    if not source_pdf.is_file():
        raise FileNotFoundError(f"source PDF not found: {source_pdf}")
    requested = sorted(set(page_numbers))
    if not requested or any(page < 1 for page in requested):
        raise ValueError("page_numbers must contain positive one-based page numbers")
    executable = shutil.which("pdftoppm")
    if executable is None:
        raise RuntimeError("pdftoppm is required but was not found on PATH")
    output_dir.mkdir(parents=True, exist_ok=True)
    rendered: list[Path] = []
    for page_number in requested:
        prefix = output_dir / f"note-page-{page_number:02d}"
        command = [
            executable,
            "-f",
            str(page_number),
            "-l",
            str(page_number),
            "-singlefile",
            "-png",
            "-r",
            str(dpi),
            str(source_pdf),
            str(prefix),
        ]
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            raise RuntimeError(
                f"PDF rendering failed for page {page_number}: {completed.stderr.strip()}"
            )
        image = prefix.with_suffix(".png")
        if not image.is_file():
            raise RuntimeError(f"PDF rendering produced no image for page {page_number}")
        rendered.append(image)
    return rendered
