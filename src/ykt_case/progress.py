# Bu dosya, terminal ilerleme çubuklarını tek noktadan açmak, kapatmak ve standartlaştırmak için kullanılır.
"""Small tqdm adapter shared by CLI pipeline stages."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TypeVar

from tqdm import tqdm


T = TypeVar("T")
_progress_enabled = False


def configure_progress(enabled: bool) -> None:
    """Enable terminal progress for the current process."""

    global _progress_enabled
    _progress_enabled = bool(enabled)


def track(
    items: Iterable[T],
    *,
    description: str,
    total: int | None = None,
    unit: str = "öğe",
    leave: bool = False,
):
    """Wrap a measurable iterable without inventing progress percentages."""

    return tqdm(
        items,
        desc=description,
        total=total,
        unit=unit,
        disable=not _progress_enabled,
        dynamic_ncols=True,
        leave=leave,
    )


def progress_bar(*, total: int, description: str, unit: str = "öğe"):
    """Create a manually advanced progress bar for coarse pipeline stages."""

    return tqdm(
        total=total,
        desc=description,
        unit=unit,
        disable=not _progress_enabled,
        dynamic_ncols=True,
        leave=True,
    )


def progress_message(message: str) -> None:
    """Write a status line without corrupting an active progress bar."""

    if _progress_enabled:
        tqdm.write(message)
