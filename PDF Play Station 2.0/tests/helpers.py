"""Shared test helpers: dummy PDFs made on the fly (no real data)."""

import sys
from pathlib import Path

import pymupdf
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services import ocr  # noqa: E402

LINE = "The quick brown fox jumps over the lazy dog."


def make_pdf(path: Path, pages: int = 5, text: str = "Page {n}", toc: bool = False) -> Path:
    doc = pymupdf.open()
    for n in range(1, pages + 1):
        p = doc.new_page()
        p.insert_text((72, 100), text.format(n=n), fontsize=14)
        p.insert_text((72, 130), f"MARKER-{n:03d}", fontsize=11)
    if toc:
        doc.set_toc([[1, f"Chapter {n}", n] for n in range(1, pages + 1)])
    doc.save(str(path))
    doc.close()
    return path


def page_markers(path, password: str = "") -> list[str]:
    with pymupdf.open(str(path)) as doc:
        if doc.needs_pass:
            doc.authenticate(password)
        out = []
        for page in doc:
            words = [w[4] for w in page.get_text("words") if w[4].startswith("MARKER-")]
            out.append(words[0] if words else "")
        return out


def rotations(path) -> list[int]:
    with pymupdf.open(str(path)) as doc:
        return [p.rotation for p in doc]


requires_tesseract = pytest.mark.skipif(not ocr.status().available or "osd" not in ocr.status().languages,
                                        reason="Tesseract with osd data is not installed")
