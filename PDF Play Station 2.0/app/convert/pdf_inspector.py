"""Fast PDF validation and page classification using PDFium.

Used when files are added to the queue (page count, scanned/text status,
encryption) and as the first step of every conversion.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c

from .validators import is_pdf_header

log = logging.getLogger(__name__)

# PDFium is not thread-safe. Every call into it (inspection in the queue
# thread, rendering in the conversion thread) holds this lock.
PDFIUM_LOCK = threading.RLock()

MIN_TEXT_CHARS = 10          # fewer visible characters than this = "no usable text"
SCANNED_IMAGE_COVERAGE = 0.25
MIXED_IMAGE_COVERAGE = 0.5

KIND_LABELS = {"text": "Text", "scanned": "Scanned", "mixed": "Text + image", "blank": "Blank"}


class PdfError(Exception):
    """A PDF problem with a message that can be shown to the user.

    ``kind`` is one of: missing, unreadable, not_pdf, corrupt, password,
    wrong_password, empty.
    """

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


@dataclass
class PdfInfo:
    path: Path
    size_bytes: int = 0
    page_count: int = 0
    encrypted: bool = False
    page_kinds: list[str] = field(default_factory=list)
    error: Optional[PdfError] = None

    @property
    def ok(self) -> bool:
        return self.error is None

    @property
    def needs_password(self) -> bool:
        return self.error is not None and self.error.kind in ("password", "wrong_password")

    def count(self, kind: str) -> int:
        return sum(1 for k in self.page_kinds if k == kind)

    @property
    def doc_type(self) -> str:
        if not self.page_kinds:
            return "Unknown"
        kinds = set(self.page_kinds) - {"blank"}
        if not kinds:
            return "Blank"
        if kinds == {"scanned"}:
            return "Scanned"
        if "scanned" in kinds:
            return "Mixed"
        if kinds == {"mixed"}:
            return "Text + image"
        return "Text"

    @property
    def needs_ocr(self) -> bool:
        return self.count("scanned") > 0


def classify_page(text_chars: int, image_coverage: float) -> str:
    if text_chars >= MIN_TEXT_CHARS:
        return "mixed" if image_coverage >= MIXED_IMAGE_COVERAGE else "text"
    if image_coverage >= SCANNED_IMAGE_COVERAGE:
        return "scanned"
    return "text" if text_chars > 0 else "blank"


def _image_coverage(page: pdfium.PdfPage, width: float, height: float) -> float:
    area = 0.0
    page_area = max(width * height, 1.0)
    try:
        for obj in page.get_objects(filter=(pdfium_c.FPDF_PAGEOBJ_IMAGE,), max_depth=4):
            bounds = obj.get_bounds() if hasattr(obj, "get_bounds") else obj.get_pos()  # pypdfium2 5.x / 4.x
            left, bottom, right, top = bounds
            left, right = max(0.0, left), min(width, right)
            bottom, top = max(0.0, bottom), min(height, top)
            if right > left and top > bottom:
                area += (right - left) * (top - bottom)
    except pdfium.PdfiumError:
        return 0.0
    return min(area / page_area, 1.0)


def open_pdfium(path: Path, password: Optional[str] = None) -> pdfium.PdfDocument:
    """Open with PDFium, translating errors into PdfError."""
    if not path.exists():
        raise PdfError("missing", "The file no longer exists or has been moved.")
    if not path.is_file():
        raise PdfError("unreadable", "The selected item is not a file.")
    try:
        with path.open("rb"):
            pass
    except OSError as exc:
        raise PdfError("unreadable", f"The file cannot be opened ({exc.strerror or exc}). "
                                     "It may be open in another program or you may lack permission.") from exc
    if path.stat().st_size == 0:
        raise PdfError("empty", "The file is empty (0 bytes).")
    if not is_pdf_header(path):
        raise PdfError("not_pdf", "The file is not a valid PDF (missing PDF header).")
    try:
        return pdfium.PdfDocument(str(path), password=password or None)
    except pdfium.PdfiumError as exc:
        code = getattr(exc, "err_code", None)
        if code == pdfium_c.FPDF_ERR_PASSWORD:
            if password:
                raise PdfError("wrong_password", "The password is incorrect.") from exc
            raise PdfError("password", "The PDF is password-protected.") from exc
        if code == pdfium_c.FPDF_ERR_SECURITY:
            raise PdfError("corrupt", "The PDF uses an unsupported security handler.") from exc
        raise PdfError("corrupt", "The PDF is damaged or not a valid PDF file.") from exc


def inspect_pdf(path: Path, password: Optional[str] = None) -> PdfInfo:
    """Inspect a PDF. Never raises: problems are reported in ``info.error``."""
    with PDFIUM_LOCK:
        return _inspect(Path(path), password)


def _inspect(path: Path, password: Optional[str]) -> PdfInfo:
    info = PdfInfo(path=path)
    try:
        info.size_bytes = path.stat().st_size
    except OSError:
        pass
    try:
        doc = open_pdfium(path, password)
    except PdfError as exc:
        info.error = exc
        info.encrypted = exc.kind in ("password", "wrong_password")
        return info
    try:
        info.encrypted = bool(password)
        info.page_count = len(doc)
        if info.page_count == 0:
            info.error = PdfError("empty", "The PDF does not contain any pages.")
            return info
        for index in range(info.page_count):
            page = doc[index]
            try:
                width, height = page.get_size()
                textpage = page.get_textpage()
                try:
                    text = textpage.get_text_range()
                finally:
                    textpage.close()
                chars = sum(1 for ch in text if not ch.isspace())
                info.page_kinds.append(classify_page(chars, _image_coverage(page, width, height)))
            except pdfium.PdfiumError:
                log.warning("Could not inspect page %s of %s", index + 1, path.name, exc_info=True)
                info.page_kinds.append("unknown")
            finally:
                page.close()
    except pdfium.PdfiumError as exc:
        log.warning("Inspection failed for %s", path.name, exc_info=True)
        info.error = PdfError("corrupt", f"The PDF could not be read completely ({exc}).")
    finally:
        doc.close()
    return info
