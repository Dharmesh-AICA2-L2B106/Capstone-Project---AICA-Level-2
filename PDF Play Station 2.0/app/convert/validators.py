"""Input validation: page ranges, file names, sheet names and folders."""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Optional


class ValidationError(ValueError):
    """Raised with a message that is safe to show to the user."""


# ---------------------------------------------------------------- page ranges

_RANGE_PART = re.compile(r"^(\d+)\s*(?:-\s*(\d+))?$")


def parse_page_range(text: str) -> Optional[list[tuple[int, int]]]:
    """Parse "1, 3-5, 8-10" into [(1, 1), (3, 5), (8, 10)].

    Returns None for an empty string (meaning "all pages").
    Raises ValidationError with a user-readable message on bad syntax.
    """
    text = (text or "").strip()
    if not text:
        return None
    parts: list[tuple[int, int]] = []
    for raw in re.split(r"[,;]", text):
        piece = raw.strip()
        if not piece:
            raise ValidationError(f'Page range "{text}" contains an empty entry. Use a format such as 1, 3-5, 8-10.')
        m = _RANGE_PART.match(piece)
        if not m:
            raise ValidationError(f'"{piece}" is not a valid page or page range. Use a format such as 1, 3-5, 8-10.')
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) else start
        if start < 1:
            raise ValidationError("Page numbers start at 1.")
        if end < start:
            raise ValidationError(f'In "{piece}" the first page is greater than the last page.')
        parts.append((start, end))
    return parts


def max_page_in_range(ranges: Optional[list[tuple[int, int]]]) -> int:
    return max((end for _, end in ranges), default=0) if ranges else 0


def pages_for_document(ranges: Optional[list[tuple[int, int]]], page_count: int) -> list[int]:
    """Sorted, de-duplicated list of 1-based page numbers.

    Raises ValidationError if the range exceeds the document's page count.
    """
    if page_count <= 0:
        raise ValidationError("The PDF does not contain any pages.")
    if ranges is None:
        return list(range(1, page_count + 1))
    highest = max_page_in_range(ranges)
    if highest > page_count:
        raise ValidationError(
            f"The page range refers to page {highest}, but this PDF has only {page_count} page(s).")
    pages = sorted({p for start, end in ranges for p in range(start, end + 1)})
    return pages


# ---------------------------------------------------------------- file names

_WIN_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
_BAD_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_filename(name: str, fallback: str = "Converted") -> str:
    """Return a valid Windows file name stem (without extension)."""
    cleaned = _BAD_FILENAME_CHARS.sub("_", name).strip().rstrip(". ")
    if not cleaned:
        cleaned = fallback
    if cleaned.split(".")[0].upper() in _WIN_RESERVED:
        cleaned = f"_{cleaned}"
    return cleaned[:150]


# ---------------------------------------------------------------- sheet names

_BAD_SHEET_CHARS = re.compile(r"[\[\]:*?/\\]")


def safe_sheet_name(name: str, existing: set[str], fallback: str = "Sheet") -> str:
    """Excel sheet names: max 31 chars, no []:*?/\\, not blank, unique
    (case-insensitive), must not start/end with an apostrophe and must not
    be the reserved name "History"."""
    cleaned = _BAD_SHEET_CHARS.sub("_", name or "").strip().strip("'")
    if not cleaned or cleaned.lower() == "history":
        cleaned = fallback
    cleaned = cleaned[:31]
    lowered = {e.lower() for e in existing}
    candidate = cleaned
    n = 2
    while candidate.lower() in lowered:
        suffix = f"_{n}"
        candidate = cleaned[: 31 - len(suffix)] + suffix
        n += 1
    existing.add(candidate)
    return candidate


# ---------------------------------------------------------------- folders

def check_output_folder(folder: Path) -> None:
    """Raise ValidationError if the folder does not exist or is not writable."""
    if not str(folder).strip():
        raise ValidationError("Please choose an output folder.")
    if not folder.exists():
        raise ValidationError(f"The output folder does not exist:\n{folder}")
    if not folder.is_dir():
        raise ValidationError(f"The output location is not a folder:\n{folder}")
    try:
        fd, probe = tempfile.mkstemp(prefix=".pcp_write_test_", dir=folder)
        os.close(fd)
        os.remove(probe)
    except OSError as exc:
        raise ValidationError(
            f"The output folder is not writable. Choose another folder or check its permissions.\n{folder}\n({exc.strerror or exc})"
        ) from exc


def free_disk_mb(folder: Path) -> Optional[float]:
    try:
        return shutil.disk_usage(folder).free / (1024 * 1024)
    except OSError:
        return None


def is_pdf_header(path: Path) -> bool:
    """Cheap check that the file starts with a PDF signature (within 1 KB,
    which is what PDF readers tolerate)."""
    try:
        with path.open("rb") as fh:
            return b"%PDF-" in fh.read(1024)
    except OSError:
        return False
