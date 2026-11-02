"""Shared helpers for every engine: job context, page ranges, opening and saving
PDFs safely, and output file names that never overwrite an existing file."""

from __future__ import annotations

import os
import re
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional, Sequence

import pymupdf

PDF_EXTS = (".pdf",)
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp")
MARKDOWN_EXTS = (".md", ".markdown", ".txt")


class Cancelled(Exception):
    """Raised inside an engine when the user cancels."""


class UserError(ValueError):
    """A problem the user can fix (wrong password, bad page list, ...). Shown as-is."""


class PasswordRequired(UserError):
    def __init__(self, path: str):
        super().__init__(f"'{Path(path).name}' is password-protected and the password is missing or incorrect.")
        self.path = path


@dataclass
class Job:
    """What an engine receives: progress reporting and cancellation, independent of
    whether it runs in a thread or a worker process."""
    progress: Callable[[int, int, str], None] = lambda done, total, text: None
    is_cancelled: Callable[[], bool] = lambda: False

    def step(self, done: int, total: int, text: str) -> None:
        if self.is_cancelled():
            raise Cancelled()
        self.progress(done, total, text)


@dataclass
class Result:
    files: list[str] = field(default_factory=list)
    message: str = ""
    warnings: list[str] = field(default_factory=list)
    details: list[str] = field(default_factory=list)     # extra lines for the result panel
    confirm: Optional[dict] = None                       # a plan the user must approve first

    def as_dict(self) -> dict:
        return {"files": self.files, "message": self.message, "warnings": self.warnings,
                "details": self.details, "confirm": self.confirm}


# ------------------------------------------------------------------ page ranges

def parse_page_groups(text: str, total: int) -> list[list[int]]:
    """'1, 3-5, 8-end' -> [[1], [3, 4, 5], [8, ..., total]] (one-based, order kept).

    'end' / 'last' mean the last page; descending ranges (10-1) are allowed."""
    s = (text or "").strip().lower()
    for dash in ("–", "—", "−"):
        s = s.replace(dash, "-")
    s = re.sub(r"\s+", "", s)
    if not s:
        raise UserError("Please enter page numbers or ranges, e.g. 1, 3-5, 8-10")
    if total < 1:
        raise UserError("The PDF has no pages.")
    groups: list[list[int]] = []
    for part in re.split(r"[,;]+", s):
        if not part:
            continue
        if part.startswith("-") or "--" in part:
            raise UserError(f"'{part}': negative page numbers are not allowed.")
        m = re.fullmatch(r"(\d+|end|last)(?:-(\d+|end|last))?", part)
        if not m:
            raise UserError(f"'{part}' is not valid. Use numbers and ranges such as 1, 3-5, 8-end.")
        a = total if m.group(1) in ("end", "last") else int(m.group(1))
        b = a if not m.group(2) else (total if m.group(2) in ("end", "last") else int(m.group(2)))
        for p in (a, b):
            if p < 1:
                raise UserError(f"Page numbers start at 1 ('{part}').")
            if p > total:
                raise UserError(f"Page {p} is out of range - the PDF has {total} page(s).")
        step = 1 if b >= a else -1
        groups.append(list(range(a, b + step, step)))
    if not groups:
        raise UserError("Please enter page numbers or ranges, e.g. 1, 3-5, 8-10")
    return groups


def parse_pages(text: str, total: int, blank_means_all: bool = True) -> list[int]:
    """One-based page list; duplicates removed (first occurrence kept)."""
    if not (text or "").strip() and blank_means_all:
        return list(range(1, total + 1))
    seen, out = set(), []
    for p in (p for g in parse_page_groups(text, total) for p in g):
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def page_runs(pages: Sequence[int]) -> list[tuple[int, int]]:
    """[1,2,3,7,6,5] -> [(1,3),(7,5)] so consecutive pages are copied in one call."""
    runs: list[tuple[int, int]] = []
    for p in pages:
        if runs:
            a, b = runs[-1]
            step = 1 if b >= a else -1
            if (a == b and abs(p - b) == 1) or (a != b and p == b + step):
                runs[-1] = (a, p)
                continue
        runs.append((p, p))
    return runs


# ------------------------------------------------------------------ files

def safe_filename(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", (name or "").strip())
    return name.strip(" .")


def same_path(a, b) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def natural_key(text: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(text))]


def unique_path(path: Path, taken: Optional[set] = None) -> Path:
    """'a.pdf' -> 'a (2).pdf' ... the first name that does not exist and is not taken."""
    taken = taken if taken is not None else set()
    path = Path(path)
    cand, i = path, 2
    while cand.exists() or str(cand).lower() in taken:
        cand = path.with_name(f"{path.stem} ({i}){path.suffix}")
        i += 1
    taken.add(str(cand).lower())
    return cand


def output_path(source: Path, out_dir: str, suffix: str, ext: str, taken: Optional[set] = None,
                name: str = "") -> Path:
    """New output file next to the source (or in out_dir), never overwriting anything."""
    folder = Path(out_dir) if out_dir else Path(source).parent
    folder.mkdir(parents=True, exist_ok=True)
    stem = safe_filename(Path(name).stem) if name else f"{Path(source).stem}{suffix}"
    return unique_path(folder / f"{stem or 'Output'}{ext}", taken)


def remove_quietly(path) -> None:
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


def write_atomic(path: Path, data: bytes) -> None:
    tmp = Path(path).with_name(f".{Path(path).name}.{secrets.token_hex(4)}.part")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    except PermissionError:
        remove_quietly(tmp)
        raise UserError(f"Cannot write '{path}'. The file may be open in another program, "
                        "or the folder is read-only.")
    except Exception:
        remove_quietly(tmp)
        raise


# ------------------------------------------------------------------ PDFs

def is_encrypted(path) -> bool:
    try:
        with pymupdf.open(path) as doc:
            return bool(doc.needs_pass)
    except Exception:
        return False


def check_password(path, password: str) -> bool:
    try:
        with pymupdf.open(path) as doc:
            return not doc.needs_pass or bool(doc.authenticate(password or ""))
    except Exception:
        return False


def open_pdf(path, password: str = "") -> pymupdf.Document:
    """Open a PDF (authenticating if needed) with readable error messages."""
    path = str(path)
    name = os.path.basename(path)
    if not os.path.isfile(path):
        raise UserError(f"File not found: {path}")
    try:
        doc = pymupdf.open(path)
    except Exception as exc:
        raise UserError(f"'{name}' could not be opened - it may be damaged ({exc}).")
    if not doc.is_pdf:
        doc.close()
        raise UserError(f"'{name}' is not a PDF file.")
    if doc.needs_pass and not doc.authenticate(password or ""):
        doc.close()
        raise PasswordRequired(path)
    if doc.page_count == 0:
        doc.close()
        raise UserError(f"'{name}' has no pages.")
    return doc


def save_pdf(doc: pymupdf.Document, path, **kwargs) -> None:
    """Full (non-incremental) save to a temporary file in the target folder, then an
    atomic replace - a failure never leaves a half-written output behind."""
    path = str(path)
    folder = os.path.dirname(os.path.abspath(path))
    tmp = os.path.join(folder, f".{os.path.basename(path)}.{secrets.token_hex(4)}.part")
    opts = {"garbage": 3, "deflate": True}
    opts.update(kwargs)
    try:
        doc.save(tmp, **opts)
        os.replace(tmp, path)
    except PermissionError:
        remove_quietly(tmp)
        raise UserError(f"Cannot write '{path}'. The file may be open in another program, "
                        "or the folder is read-only.")
    except Exception:
        remove_quietly(tmp)
        raise
