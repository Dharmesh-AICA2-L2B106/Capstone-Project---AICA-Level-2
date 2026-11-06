"""Page-by-page content extraction (native text, tables and OCR).

Each page is classified on its own, so a PDF that mixes scanned and
text-based pages is handled correctly. Pages that cannot be processed are
never silently dropped: they are kept in the result with a warning.
"""

from __future__ import annotations

import logging
import re
import statistics
from pathlib import Path
from typing import Any, Callable, Optional

import pdfplumber
import pypdfium2 as pdfium

from .layout import analyse_words
from .models import DocumentContent, PageContent, Word
from .ocr_engine import OcrEngine, OcrError
from .pdf_inspector import PDFIUM_LOCK, PdfError, classify_page
from .settings import ConversionSettings
from .table_extractor import extract_ruled_tables, words_outside

log = logging.getLogger(__name__)

PREVIEW_DPI = 150
MAX_RENDER_PIXELS = 7000          # longest side; protects memory on huge pages
LOW_OCR_CONFIDENCE = 70.0

_BOLD = re.compile(r"bold|black|heavy|semibold|demibold|extrabold", re.I)
_ITALIC = re.compile(r"italic|oblique|slanted", re.I)
_SUBSET = re.compile(r"^[A-Z]{6}\+")
_SYMBOL_FONT = re.compile(r"dingbat|symbol|wingding", re.I)
_CID_ONLY = re.compile(r"^\(cid:(\d+)\)$")
_BULLET_CODES = {"127", "149", "183"}   # common bullet positions in single-byte encodings


class Cancelled(Exception):
    pass


ProgressFn = Callable[[int, int, int, str], None]   # (page_no, index, total, stage)


def font_family(fontname: str) -> str:
    """'ABCDEF+Arial-BoldMT' -> 'Arial'. Used only as a hint for Word output."""
    name = _SUBSET.sub("", fontname or "")
    name = re.split(r"[-,]", name)[0]
    name = re.sub(r"(MT|PS|Std|Pro)$", "", name)
    mapping = {"helvetica": "Arial", "arial": "Arial", "arialmt": "Arial", "times": "Times New Roman",
               "timesnewroman": "Times New Roman", "timesnewromanps": "Times New Roman", "courier": "Courier New",
               "couriernew": "Courier New", "calibri": "Calibri", "cambria": "Cambria", "verdana": "Verdana",
               "tahoma": "Tahoma", "georgia": "Georgia", "segoeui": "Segoe UI", "garamond": "Garamond",
               "bookantiqua": "Book Antiqua", "century": "Century", "centurygothic": "Century Gothic"}
    return mapping.get(name.lower().replace(" ", ""), "")


def _is_password_error(exc: BaseException) -> bool:
    seen: Optional[BaseException] = exc
    while seen is not None:
        if "PDFPasswordIncorrect" in type(seen).__name__ or "password" in str(seen).lower():
            return True
        for arg in getattr(seen, "args", ()):
            if isinstance(arg, BaseException) and _is_password_error(arg):
                return True
        seen = seen.__cause__ or seen.__context__
    return False


def open_plumber(path: Path, password: Optional[str]) -> Any:
    try:
        pdf = pdfplumber.open(str(path), password=password or "")
        _ = len(pdf.pages)          # forces the page tree to load
        return pdf
    except Exception as exc:
        if _is_password_error(exc):
            raise PdfError("wrong_password" if password else "password",
                           "The password is incorrect." if password else "The PDF is password-protected.") from exc
        raise PdfError("corrupt", "The PDF structure could not be read (the file may be damaged).") from exc


class DocumentExtractor:
    def __init__(self, path: Path, settings: ConversionSettings, ocr: OcrEngine, temp_dir: Path,
                 password: Optional[str] = None, progress: Optional[ProgressFn] = None,
                 is_cancelled: Callable[[], bool] = lambda: False):
        self.path = Path(path)
        self.settings = settings
        self.ocr = ocr
        self.temp_dir = Path(temp_dir)
        self.password = password
        self.progress = progress or (lambda *a: None)
        self.is_cancelled = is_cancelled
        self._pdfium: Optional[pdfium.PdfDocument] = None
        self._ocr_status = ocr.detect() if settings.ocr_mode != "off" else None

    # ------------------------------------------------------------ public

    def extract(self, pages: list[int]) -> DocumentContent:
        pdf = open_plumber(self.path, self.password)
        doc = DocumentContent(source=self.path, page_count=len(pdf.pages))
        try:
            for index, page_no in enumerate(pages):
                if self.is_cancelled():
                    raise Cancelled()
                self.progress(page_no, index, len(pages), "Reading page")
                page = pdf.pages[page_no - 1]
                try:
                    content = self._extract_page(page, page_no, index, len(pages))
                except Cancelled:
                    raise
                except Exception as exc:
                    log.exception("Page %s of %s could not be processed", page_no, self.path.name)
                    content = PageContent(page_no, float(page.width), float(page.height), kind="unknown",
                                          method="none")
                    content.warnings.append(f"Page {page_no}: could not be processed ({type(exc).__name__}).")
                finally:
                    try:
                        page.close()
                    except Exception:
                        pass
                if not content.has_content and not content.warnings:
                    content.warnings.append(f"Page {page_no}: no meaningful text was extracted.")
                doc.pages.append(content)
        finally:
            pdf.close()
            if self._pdfium is not None:
                with PDFIUM_LOCK:
                    self._pdfium.close()
                self._pdfium = None
        for page in doc.pages:
            doc.warnings.extend(page.warnings)
        return doc

    # ------------------------------------------------------------ pages

    def _extract_page(self, page: Any, page_no: int, index: int, total: int) -> PageContent:
        s = self.settings
        width, height = float(page.width), float(page.height)
        content = PageContent(page_no, width, height)

        chars = [c for c in page.chars if c.get("text", "").strip()]
        cid = sum(1 for c in chars if c["text"].startswith("(cid:") or c["text"] == "�")
        garbled = bool(chars) and cid / len(chars) > 0.3
        content.kind = classify_page(len(chars), self._image_coverage(page, width, height))

        ocr_ok = bool(self._ocr_status and self._ocr_status.available)
        wants_ocr = s.ocr_mode == "always" or (s.ocr_mode == "auto" and (content.kind == "scanned" or garbled))

        if wants_ocr and ocr_ok:
            self.progress(page_no, index, total, "Running OCR")
            self._ocr_page(content)
            if content.method == "none" and chars and not garbled:
                content.warnings.append(f"Page {page_no}: used the PDF's own text layer instead.")
                self._native_page(page, content)
        else:
            if content.kind == "scanned" or garbled:
                reason = ("OCR is turned off" if s.ocr_mode == "off"
                          else "the OCR engine (Tesseract) is not available")
                what = "appears to be scanned" if content.kind == "scanned" else "contains unreadable (unmapped) characters"
                content.warnings.append(f"Page {page_no} {what}, but {reason}; its text could not be extracted.")
            if content.kind != "scanned":
                self._native_page(page, content)
            else:
                content.method = "none"
            if content.kind == "scanned" and s.want_word:
                content.image_path = self._render_to_file(page_no, PREVIEW_DPI)
        if content.kind == "mixed" and content.method == "text" and s.ocr_mode != "always":
            content.warnings.append(
                f"Page {page_no} contains a large image; any text inside the image is not extracted "
                "unless OCR is set to 'Always run OCR'.")
        if content.kind == "blank":
            content.warnings.append(f"Page {page_no}: no text found (the page appears to be blank).")
        if s.want_word and s.word_mode == "layout" and content.image_path is None:
            content.image_path = self._render_to_file(page_no, PREVIEW_DPI)
        return content

    def _native_page(self, page: Any, content: PageContent) -> None:
        s = self.settings
        content.method = "text"
        raw = page.extract_words(x_tolerance=1.5, y_tolerance=2.5, keep_blank_chars=False,
                                 use_text_flow=False, extra_attrs=["fontname", "size"])
        links = []
        try:
            links = [(h.get("uri"), h["x0"], h["top"], h["x1"], h["bottom"]) for h in page.hyperlinks if h.get("uri")]
        except Exception:
            log.debug("Hyperlinks unavailable on page %s", content.number, exc_info=True)
        words: list[Word] = []
        for w in raw:
            fontname = w.get("fontname", "")
            text = w["text"]
            cid = _CID_ONLY.match(text)
            if cid and (_SYMBOL_FONT.search(fontname) or cid.group(1) in _BULLET_CODES):
                # A lone unmapped glyph from a symbol font, or at a bullet code
                # point, is a list bullet in practice; show it as one rather
                # than "(cid:127)". Other unmapped glyphs are left as-is.
                text = "•"
            word = Word(text, float(w["x0"]), float(w["x1"]), float(w["top"]), float(w["bottom"]),
                        size=float(w.get("size") or 10.0), fontname=font_family(fontname),
                        bold=bool(_BOLD.search(fontname)), italic=bool(_ITALIC.search(fontname)))
            for uri, x0, top, x1, bottom in links:
                if x0 - 1 <= word.xc <= x1 + 1 and top - 1 <= word.yc <= bottom + 1:
                    word.link = uri
                    break
            words.append(word)

        undecoded = sum(w.text.count("(cid:") for w in words)
        if undecoded:
            content.warnings.append(
                f"Page {content.number}: {undecoded} character(s) have no text mapping in the PDF font and are "
                "shown as (cid:N). Compare with the original.")

        ruled = extract_ruled_tables(page, content.number) if s.table_method in ("auto", "lines") else []
        remaining = words_outside(words, ruled)
        content.items = analyse_words(remaining, content.number, content.width, ruled,
                                      detect_tables=s.table_method in ("auto", "text"))
        if words:
            content.margins = (min(w.x0 for w in words), min(w.top for w in words),
                               content.width - max(w.x1 for w in words), content.height - max(w.bottom for w in words))

    def _ocr_page(self, content: PageContent) -> None:
        s = self.settings
        content.method = "ocr"
        image, dpi = self._render(content.number, s.ocr_dpi)
        try:
            ocr_words = self.ocr.recognise(image, s.ocr_language, timeout=s.ocr_timeout_seconds)
        except OcrError as exc:
            content.method = "none"
            content.warnings.append(f"Page {content.number}: {exc}")
            ocr_words = []
        scale = 72.0 / dpi
        # Tesseract boxes fit the glyphs of each word; use the tallest word in
        # each recognised line as the line's font size estimate.
        line_height: dict[tuple[int, int, int], float] = {}
        for w in ocr_words:
            line_height[w.line_key] = max(line_height.get(w.line_key, 0.0), w.height * scale)
        words = [Word(w.text, w.left * scale, (w.left + w.width) * scale, w.top * scale,
                      (w.top + w.height) * scale, size=max(line_height[w.line_key] / 0.9, 4.0), conf=w.conf)
                 for w in ocr_words]
        if words:
            content.items = analyse_words(words, content.number, content.width, [], detect_tables=True,
                                          table_source="ocr")
            content.ocr_confidence = round(statistics.mean(w.conf for w in words), 1)
            content.margins = (min(w.x0 for w in words), min(w.top for w in words),
                               content.width - max(w.x1 for w in words), content.height - max(w.bottom for w in words))
            if content.ocr_confidence < LOW_OCR_CONFIDENCE:
                content.warnings.append(
                    f"Page {content.number}: OCR confidence is low ({content.ocr_confidence:.0f}%). "
                    "Check the recognised text carefully.")
        elif content.method == "ocr":
            content.warnings.append(f"Page {content.number}: OCR did not recognise any text.")
        if s.want_word and (s.preserve_scanned_images or s.word_mode == "layout" or not words):
            content.image_path = self._save_image(image, dpi, content.number)
        image.close()

    # ------------------------------------------------------------ helpers

    @staticmethod
    def _image_coverage(page: Any, width: float, height: float) -> float:
        area = 0.0
        for img in page.images:
            x0, x1 = max(0.0, float(img["x0"])), min(width, float(img["x1"]))
            top, bottom = max(0.0, float(img["top"])), min(height, float(img["bottom"]))
            if x1 > x0 and bottom > top:
                area += (x1 - x0) * (bottom - top)
        return min(area / max(width * height, 1.0), 1.0)

    def _pdfium_doc(self) -> pdfium.PdfDocument:
        if self._pdfium is None:
            self._pdfium = pdfium.PdfDocument(str(self.path), password=self.password or None)
        return self._pdfium

    def _render(self, page_no: int, dpi: int):
        with PDFIUM_LOCK:
            page = self._pdfium_doc()[page_no - 1]
            try:
                w, h = page.get_size()
                scale = dpi / 72.0
                longest = max(w, h) * scale
                if longest > MAX_RENDER_PIXELS:
                    scale *= MAX_RENDER_PIXELS / longest
                image = page.render(scale=scale).to_pil()
                return image, scale * 72.0
            finally:
                page.close()

    def _save_image(self, image, dpi: float, page_no: int) -> Path:
        target = self.temp_dir / f"page_{page_no:04d}.jpg"
        out = image
        if dpi > PREVIEW_DPI + 1:
            ratio = PREVIEW_DPI / dpi
            out = image.resize((max(1, int(image.width * ratio)), max(1, int(image.height * ratio))))
        out.convert("RGB").save(target, "JPEG", quality=85)
        return target

    def _render_to_file(self, page_no: int, dpi: int) -> Optional[Path]:
        try:
            image, real_dpi = self._render(page_no, dpi)
            try:
                return self._save_image(image, real_dpi, page_no)
            finally:
                image.close()
        except Exception:
            log.warning("Could not render page %s of %s", page_no, self.path.name, exc_info=True)
            return None
