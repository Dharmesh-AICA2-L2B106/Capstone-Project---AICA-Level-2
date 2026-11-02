"""Section 3 engines: finding sensitive data, secure redaction and verification.

Ported from the earlier PDF Play Station (v1.1.0) - the redaction method, the
engine self-test and the verification checks are unchanged. New in 2.0:
  * eight more Smart Redaction categories (GSTIN with its check character, TAN,
    CIN, DIN, IFSC, passport, voter ID, date of birth);
  * OCR for scanned pages (English / Hindi / Marathi): words and their positions
    are read with Tesseract, so Find and Smart Redaction work on scans;
  * verification also proves that every redacted area is blacked out in the saved
    file, and (with OCR) that redacted values cannot be read from scanned pages.

All rectangles are in unrotated PDF page coordinates (PyMuPDF's redaction space).
"""

from __future__ import annotations

import io
import math
import re
from typing import Optional, Sequence

import pymupdf

from . import ocr
from .common import Job, UserError, open_pdf, same_path, save_pdf

TEXT_FLAGS = (pymupdf.TEXT_PRESERVE_WHITESPACE | pymupdf.TEXT_PRESERVE_LIGATURES |
              getattr(pymupdf, "TEXT_MEDIABOX_CLIP", 0))
MATCH_PAD = 0.75                 # points of padding around matched text
MAX_RESULTS = 20000
OCR_DPI = 300

CATEGORIES = ["PAN", "Aadhaar", "GSTIN", "TAN", "CIN", "DIN", "Bank account numbers", "IFSC", "Passport",
              "Voter ID", "Mobile numbers", "E-mail addresses", "Dates of birth"]


# ================================================================== small helpers

def mask_value(text: str) -> str:
    """Show the first and last two letters/digits, mask the rest."""
    chars = [c for c in text if c.isalnum()]
    if len(chars) <= 4:
        return "•" * len(text)
    keep = set(range(2)) | set(range(len(chars) - 2, len(chars)))
    out, k = [], 0
    for c in text:
        if c.isalnum():
            out.append(c if k in keep else "•")
            k += 1
        else:
            out.append(c)
    return "".join(out)


def normalise(text: str) -> str:
    return re.sub(r"[\s\- ]+", "", text or "").casefold()


def _context(text: str, start: int, end: int) -> str:
    s, e = max(0, start - 30), min(len(text), end + 30)
    return ("..." if s else "") + text[s:e].strip() + ("..." if e < len(text) else "")


def span_rect(text: str, boxes: list, start: int, end: int, pad: float = MATCH_PAD) -> Optional[pymupdf.Rect]:
    rect = None
    for i in range(start, min(end, len(boxes))):
        b = boxes[i]
        if text[i].isspace() or b.is_empty or b.is_infinite:
            continue
        rect = pymupdf.Rect(b) if rect is None else rect | b
    if rect is None:
        return None
    return pymupdf.Rect(rect.x0 - pad, rect.y0 - pad, rect.x1 + pad, rect.y1 + pad)


# ================================================================== text lines (text layer or OCR)

def text_lines(page: pymupdf.Page):
    """Yield (line_text, [char Rect, ...]) per text line of the text layer."""
    data = page.get_text("rawdict", flags=TEXT_FLAGS)
    for block in data.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            chars: list[str] = []
            boxes: list[pymupdf.Rect] = []
            for span in line.get("spans", []):
                for ch in span.get("chars", []):
                    box = pymupdf.Rect(ch["bbox"])
                    for c in ch.get("c", ""):
                        chars.append(c)
                        boxes.append(box)
            if chars:
                yield "".join(chars), boxes


def ocr_lines(page: pymupdf.Page, lang: str) -> list[tuple[str, list[tuple]]]:
    """OCR one page: [(line text, [char box tuple, ...])] in unrotated page space.

    Tesseract gives a box per word; it is split evenly across the word's characters
    (spaces get an empty box), which is precise enough for redaction with padding."""
    from PIL import Image
    import pytesseract
    ocr.require(lang)
    pix = page.get_pixmap(dpi=OCR_DPI, alpha=False)                     # as displayed (rotation applied)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    try:
        data = pytesseract.image_to_data(img, lang=lang, config=f"--psm 3 --dpi {OCR_DPI}", timeout=240,
                                         output_type=pytesseract.Output.DICT)
    except (RuntimeError, pytesseract.TesseractError) as exc:
        raise ocr.OcrError(f"OCR failed on page {page.number + 1}: {exc}") from exc
    scale = 72.0 / OCR_DPI
    derot = page.derotation_matrix
    lines: dict[tuple, list] = {}
    for i, word in enumerate(data["text"]):
        word = (word or "").strip()
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            conf = -1
        if not word or conf < 0:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        x, y = data["left"][i] * scale, data["top"][i] * scale
        w, h = data["width"][i] * scale, data["height"][i] * scale
        lines.setdefault(key, []).append((x, y, w, h, word))
    out = []
    for key in sorted(lines):
        words = sorted(lines[key], key=lambda t: t[0])
        text, boxes = "", []
        for n, (x, y, w, h, word) in enumerate(words):
            if n:
                text += " "
                boxes.append(tuple(pymupdf.Rect()))
            step = w / len(word)
            for k, c in enumerate(word):
                r = pymupdf.Rect(x + k * step, y, x + (k + 1) * step, y + h) * derot
                r.normalize()
                text += c
                boxes.append(tuple(r))
        out.append((text, boxes))
    return out


def page_text_lines(page: pymupdf.Page, ocr_mode: str, lang: str, cache: dict):
    """Lines from the text layer, or from OCR for pages without one (or always).
    Returns (lines, used_ocr). OCR results are kept in `cache` ({page: lines})."""
    has_text = bool(page.get_text("text").strip())
    use_ocr = ocr_mode == "Always run OCR" or (not has_text and ocr_mode != "Off")
    if not use_ocr:
        return [(t, b) for t, b in text_lines(page)], False
    key = str(page.number)
    if key not in cache:
        cache[key] = ocr_lines(page, lang)
    return [(t, [pymupdf.Rect(b) for b in boxes]) for t, boxes in cache[key]], True


# ================================================================== validators

class AadhaarValidator:
    """Verhoeff checksum (the 12th Aadhaar digit is a Verhoeff check digit).
    A valid checksum does not prove that the number was issued or who holds it."""
    D = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
         [2, 3, 4, 0, 1, 7, 8, 9, 5, 6], [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
         [4, 0, 1, 2, 3, 9, 5, 6, 7, 8], [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
         [6, 5, 9, 8, 7, 1, 0, 4, 3, 2], [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
         [8, 7, 6, 5, 9, 3, 2, 1, 0, 4], [9, 8, 7, 6, 5, 4, 3, 2, 1, 0]]
    P = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
         [5, 8, 0, 3, 7, 9, 6, 1, 4, 2], [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
         [9, 4, 5, 3, 1, 2, 6, 8, 7, 0], [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
         [2, 7, 9, 3, 8, 0, 6, 4, 1, 5], [7, 0, 4, 6, 9, 1, 3, 2, 5, 8]]
    INV = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9]

    @classmethod
    def checksum_ok(cls, digits: str) -> bool:
        c = 0
        for i, ch in enumerate(reversed(digits)):
            c = cls.D[c][cls.P[i % 8][int(ch)]]
        return c == 0

    @classmethod
    def check_digit(cls, first11: str) -> str:
        c = 0
        for i, ch in enumerate(reversed(first11)):
            c = cls.D[c][cls.P[(i + 1) % 8][int(ch)]]
        return str(cls.INV[c])

    @classmethod
    def validate(cls, candidate: str) -> tuple[bool, str]:
        digits = re.sub(r"[\s\- ]", "", candidate)
        if not re.fullmatch(r"\d{12}", digits):
            return False, "not 12 digits"
        if len(set(digits)) == 1:
            return False, "repeated digit"
        if digits[0] in "01":
            return False, "cannot start with 0 or 1"
        if not cls.checksum_ok(digits):
            return False, "Verhoeff checksum fails"
        return True, "Verhoeff checksum valid"


GSTIN_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def gstin_check_char(first14: str) -> str:
    """GSTIN check character (15th): weighted base-36 sum of the first 14."""
    total = 0
    for i, c in enumerate(first14.upper()):
        p = GSTIN_CHARS.index(c) * (1 if i % 2 == 0 else 2)
        total += p // 36 + p % 36
    return GSTIN_CHARS[(36 - total % 36) % 36]


def gstin_valid(value: str) -> bool:
    v = value.upper()
    return bool(re.fullmatch(r"\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]", v)) and gstin_check_char(v[:14]) == v[14]


PAN_HOLDER = {"A": "AOP", "B": "BOI", "C": "Company", "F": "Firm/LLP", "G": "Government",
              "H": "HUF", "J": "Artificial juridical person", "L": "Local authority",
              "P": "Individual", "T": "Trust"}
CIN_TYPES = {"PLC", "PTC", "OPC", "LLC", "FLC", "GOI", "SGC", "NPL", "GAP", "GAT", "ULL", "ULT", "FTC"}
BANK_KEYWORDS = re.compile(r"(a\s*/\s*c\b|\bac\s*no\b|\bacc(?:oun)?t\.?\s*(?:no|number|#)|account\s*no|"
                           r"account\s*number|bank\s*account|savings\s*(?:a/?c|account)|"
                           r"current\s*(?:a/?c|account)|\bsb\s*a/?c|\bacct\b)", re.I)
PHONE_KEYWORDS = re.compile(r"(\bmob|mobile|phone|\bph\b|\btel\b|contact|\bcell|whats\s*app)", re.I)
DOB_KEYWORDS = re.compile(r"(\bd\.?\s*o\.?\s*b\b|date\s+of\s+birth|birth\s*date|born\s+on|\bborn\b|जन्म)", re.I)
RE_EMAIL = re.compile(r"(?<![A-Za-z0-9._%+\-])[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}")
RE_AADHAAR = re.compile(r"(?<![0-9])[0-9]{4}([ \- ]?)[0-9]{4}\1[0-9]{4}(?![0-9])")
RE_MOBILE = re.compile(r"(?<![0-9A-Za-z+])(\+91[ \-]?|91[ \-]|0)?([6-9][0-9]{4})([ \-]?)([0-9]{5})(?![0-9])")
RE_GSTIN = re.compile(r"(?<![A-Za-z0-9])\d{2}[A-Za-z]{5}\d{4}[A-Za-z][1-9A-Za-z][Zz][0-9A-Za-z](?![A-Za-z0-9])")
RE_CIN = re.compile(r"(?<![A-Za-z0-9])[LU]\d{5}[A-Z]{2}\d{4}([A-Z]{3})\d{6}(?![A-Za-z0-9])")
RE_TAN = re.compile(r"(?<![A-Za-z0-9])[A-Z]{4}\d{5}[A-Z](?![A-Za-z0-9])")
RE_IFSC = re.compile(r"(?<![A-Za-z0-9])[A-Z]{4}0[A-Z0-9]{6}(?![A-Za-z0-9])")
RE_VOTER = re.compile(r"(?<![A-Za-z0-9])[A-Z]{3}\d{7}(?![A-Za-z0-9])")
RE_PASSPORT = re.compile(r"(?<![A-Za-z0-9])[A-Z][1-9]\d{6}(?![A-Za-z0-9])")
RE_DIN = re.compile(r"(?<![A-Za-z0-9])\d{8}(?![A-Za-z0-9])")
MONTHS = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*"
RE_DATE = re.compile(r"(?<![0-9])(?:\d{1,2}[/\-.]\d{1,2}[/\-.](?:\d{4}|\d{2})|\d{1,2}(?:st|nd|rd|th)?[ \-]"
                     + MONTHS + r"[ \-,]*\d{4}|" + MONTHS + r"[ \-]\d{1,2},?[ \-]\d{4})(?![0-9])", re.I)


def _near(rx: re.Pattern, text: str, start: int, before: int = 40):
    return rx.search(text[max(0, start - before):start])


class DetectionSettings:
    def __init__(self, categories: Sequence[str] = CATEGORIES, pan_any_case: bool = False,
                 bank_min: int = 9, bank_max: int = 18, bank_require_keyword: bool = True,
                 mobile_require_signal: bool = False):
        self.categories = list(categories)
        self.pan_any_case = pan_any_case
        self.bank_min, self.bank_max = bank_min, bank_max
        self.bank_require_keyword = bank_require_keyword
        self.mobile_require_signal = mobile_require_signal


def detect_line(text: str, st: DetectionSettings) -> list[tuple[str, int, int, str, str]]:
    """[(category, start, end, confidence, validation note)] for one line of text.
    Results are proposals for review, not verification against any official record."""
    found: list[tuple[str, int, int, str, str]] = []
    taken: list[tuple[int, int]] = []

    def free(s: int, e: int) -> bool:
        return all(e <= a or s >= b for a, b in taken)

    def add(cat: str, s: int, e: int, conf: str, note: str) -> None:
        found.append((cat, s, e, conf, note))
        taken.append((s, e))

    cats = st.categories
    if "E-mail addresses" in cats:
        for m in RE_EMAIL.finditer(text):
            if free(m.start(), m.end()):
                add("E-mail addresses", m.start(), m.end(), "High", "E-mail pattern")
    if "GSTIN" in cats:
        for m in RE_GSTIN.finditer(text):
            if not free(m.start(), m.end()):
                continue
            v = m.group(0)
            if gstin_valid(v):
                add("GSTIN", m.start(), m.end(), "High", f"Check character valid; state code {v[:2]}")
            elif v.isupper():
                add("GSTIN", m.start(), m.end(), "Medium", "Format match; check character does not fit")
    if "CIN" in cats:
        for m in RE_CIN.finditer(text):
            if free(m.start(), m.end()):
                ok = m.group(1) in CIN_TYPES
                add("CIN", m.start(), m.end(), "High" if ok else "Medium",
                    f"Company type '{m.group(1)}'" if ok else "Format match; unknown company type")
    if "PAN" in cats:
        rx = re.compile(r"(?<![A-Za-z0-9])[A-Z]{5}[0-9]{4}[A-Z](?![A-Za-z0-9])", re.I if st.pan_any_case else 0)
        for m in rx.finditer(text):
            if not free(m.start(), m.end()):
                continue
            val = m.group(0)
            holder = PAN_HOLDER.get(val[3].upper())
            if holder and val.isupper():
                add("PAN", m.start(), m.end(), "High", f"Format match; 4th char '{val[3]}' = {holder}")
            elif holder:
                add("PAN", m.start(), m.end(), "Medium", "Format match (not upper case)")
            else:
                add("PAN", m.start(), m.end(), "Low", "Format match; 4th char not a holder type")
    if "TAN" in cats:
        for m in RE_TAN.finditer(text):
            if free(m.start(), m.end()):
                kw = _near(re.compile(r"\bTAN\b", re.I), text, m.start())
                add("TAN", m.start(), m.end(), "High" if kw else "Medium",
                    "Keyword 'TAN'" if kw else "Format match (4 letters, 5 digits, 1 letter)")
    if "IFSC" in cats:
        for m in RE_IFSC.finditer(text):
            if free(m.start(), m.end()):
                add("IFSC", m.start(), m.end(), "High", "IFSC format (5th character 0)")
    if "Voter ID" in cats:
        for m in RE_VOTER.finditer(text):
            if free(m.start(), m.end()):
                kw = _near(re.compile(r"(voter|epic|election)", re.I), text, m.start(), 50)
                add("Voter ID", m.start(), m.end(), "High" if kw else "Medium",
                    f"Keyword '{kw.group(0)}'" if kw else "EPIC format (3 letters, 7 digits)")
    if "Passport" in cats:
        for m in RE_PASSPORT.finditer(text):
            if free(m.start(), m.end()):
                kw = _near(re.compile(r"passport", re.I), text, m.start(), 50)
                add("Passport", m.start(), m.end(), "High" if kw else "Low",
                    "Keyword 'passport'" if kw else "Format only (1 letter, 7 digits)")
    if "Aadhaar" in cats:
        for m in RE_AADHAAR.finditer(text):
            ok, note = AadhaarValidator.validate(m.group(0))
            if ok and free(m.start(), m.end()):
                add("Aadhaar", m.start(), m.end(), "High", note)
    if "DIN" in cats:
        for m in RE_DIN.finditer(text):
            kw = _near(re.compile(r"\bDIN\b", re.I), text, m.start(), 25)
            if kw and free(m.start(), m.end()):
                add("DIN", m.start(), m.end(), "High", "Keyword 'DIN'")
    if "Dates of birth" in cats:
        for m in RE_DATE.finditer(text):
            kw = _near(DOB_KEYWORDS, text, m.start(), 35)
            if kw and free(m.start(), m.end()):
                add("Dates of birth", m.start(), m.end(), "High", f"Keyword '{kw.group(0).strip()}'")
    if "Mobile numbers" in cats or "Bank account numbers" in cats:
        for m in RE_MOBILE.finditer(text):
            if not free(m.start(), m.end()):
                continue
            before = text[max(0, m.start() - 40):m.start()]
            bank_kw, phone_kw = BANK_KEYWORDS.search(before), PHONE_KEYWORDS.search(before)
            prefix, sep = m.group(1), m.group(3)
            if bank_kw and not phone_kw and not prefix and not sep:
                if "Bank account numbers" in cats and st.bank_min <= 10 <= st.bank_max:
                    add("Bank account numbers", m.start(), m.end(), "High",
                        f"Keyword '{bank_kw.group(0).strip()}'")
                continue
            if "Mobile numbers" not in cats:
                continue
            if prefix or phone_kw:
                add("Mobile numbers", m.start(), m.end(), "High",
                    f"Prefix '{prefix.strip()}'" if prefix else f"Keyword '{phone_kw.group(0)}'")
            elif sep:
                add("Mobile numbers", m.start(), m.end(), "Medium", "5+5 digit grouping")
            elif not st.mobile_require_signal:
                add("Mobile numbers", m.start(), m.end(), "Low", "10 digits starting 6-9; no prefix or keyword")
    if "Bank account numbers" in cats:
        rx = re.compile(r"(?<![0-9A-Za-z])[0-9]{%d,%d}(?![0-9A-Za-z])" % (st.bank_min, st.bank_max))
        for m in rx.finditer(text):
            if not free(m.start(), m.end()) or len(set(m.group(0))) == 1:
                continue
            kw = BANK_KEYWORDS.search(text[max(0, m.start() - 45):m.start()])
            if kw:
                add("Bank account numbers", m.start(), m.end(), "High", f"Keyword '{kw.group(0).strip()}'")
            elif not st.bank_require_keyword:
                add("Bank account numbers", m.start(), m.end(), "Low", "Length rule only; no account keyword")
    return found


# ================================================================== scan / find

def _search(job: Job, path, password, matcher, ocr_mode: str, lang: str, ocr_cache: Optional[dict]) -> dict:
    cache = dict(ocr_cache or {})
    doc = open_pdf(path, password)
    results, truncated, text_pages, ocr_pages, no_text = [], False, 0, [], []
    try:
        n = doc.page_count
        for pno in range(n):
            job.step(pno, n, f"Reading page {pno + 1} of {n}")
            try:
                lines, used_ocr = page_text_lines(doc[pno], ocr_mode, lang, cache)
            except ocr.OcrError as exc:
                raise UserError(str(exc))
            if used_ocr:
                ocr_pages.append(pno + 1)
            had_text = False
            for text, boxes in lines:
                if text.strip():
                    had_text = True
                for item in matcher(text):
                    s, e = item["start"], item["end"]
                    r = span_rect(text, boxes, s, e)
                    if r is not None:
                        item.update({"text": text[s:e].strip(), "page": pno, "rect": tuple(r),
                                     "context": _context(text, s, e), "ocr": used_ocr})
                        del item["start"], item["end"]
                        results.append(item)
            text_pages += had_text
            if not had_text:
                no_text.append(pno + 1)
            if len(results) >= MAX_RESULTS:
                truncated = True
                break
    finally:
        doc.close()
    return {"results": results, "truncated": truncated, "text_pages": text_pages, "pages": n,
            "ocr_pages": ocr_pages, "no_text": no_text, "ocr_cache": cache}


def scan(job: Job, path, password: str, categories: list[str], ocr_mode: str = "Automatic (recommended)",
         ocr_lang: str = "eng", ocr_cache: Optional[dict] = None, pan_any_case: bool = False,
         bank_require_keyword: bool = True) -> dict:
    st = DetectionSettings(categories, pan_any_case=pan_any_case, bank_require_keyword=bank_require_keyword)
    if not categories:
        raise UserError("Select at least one category to detect.")

    def matcher(text):
        return [{"cat": c, "start": s, "end": e, "conf": conf, "note": note}
                for c, s, e, conf, note in detect_line(text, st)]
    return _search(job, path, password, matcher, ocr_mode, ocr_lang, ocr_cache)


def build_find_pattern(terms: list[str], match_case: bool, whole_word: bool, flexible_spaces: bool,
                       use_regex: bool = False) -> tuple[str, int]:
    """One pattern for several search terms (one per line or comma-separated)."""
    terms = [t.strip() for t in terms if t.strip()]
    if not terms:
        raise UserError("Please enter the text to find.")
    parts = []
    for term in terms:
        if use_regex:
            p = term
        else:
            words = [re.escape(w) for w in term.split()]
            if flexible_spaces and len(words) == 1:
                # '1234 5678' also finds '12345678' and '1234-5678'
                p = r"[\s\-]*".join(re.escape(c) for c in term)
            else:
                p = (r"[\s\-]*" if flexible_spaces else r"\s+").join(words)
        parts.append(f"(?:{p})")
    pattern = "|".join(parts)
    if whole_word:
        pattern = r"(?<!\w)(?:%s)(?!\w)" % pattern
    flags = 0 if match_case else re.IGNORECASE
    try:
        re.compile(pattern, flags)
    except re.error as exc:
        raise UserError(f"Invalid search pattern: {exc}")
    return pattern, flags


def find(job: Job, path, password: str, terms: list[str], match_case: bool = False, whole_word: bool = True,
         flexible_spaces: bool = True, ocr_mode: str = "Automatic (recommended)", ocr_lang: str = "eng",
         ocr_cache: Optional[dict] = None) -> dict:
    pattern, flags = build_find_pattern(terms, match_case, whole_word, flexible_spaces)
    rx = re.compile(pattern, flags)

    def matcher(text):
        return [{"cat": "Find", "start": m.start(), "end": m.end(), "conf": "", "note": "Search match"}
                for m in rx.finditer(text) if m.end() > m.start()]
    return _search(job, path, password, matcher, ocr_mode, ocr_lang, ocr_cache)


# ================================================================== secure redaction

ENGINE_ERROR = ("The installed PyMuPDF ({}) does not redact correctly: it moves the text that follows a "
                "removed word. Install a verified version: PyMuPDF>=1.24.10,<2")


def pymupdf_version() -> str:
    return str(getattr(pymupdf, "__version__", None) or getattr(pymupdf, "VersionBind", "?"))


def engine_ok() -> bool:
    """Self-test: redacting a word must remove it without moving the text after it."""
    try:
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((40, 100), "keep ABCPK1234Q stays here", fontsize=10)
        x0 = page.search_for("stays")[0].x0
        page.add_redact_annot(page.search_for("ABCPK1234Q")[0])
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_PIXELS)
        words = [w for w in page.get_text("words") if w[4] == "stays"]
        ok = bool(words) and abs(words[0][0] - x0) < 0.3 and "ABCPK" not in page.get_text()
        doc.close()
        return ok
    except Exception:
        return False


def _char_index(page) -> dict:
    index: dict = {}
    for text, boxes in text_lines(page):
        for ch, b in zip(text, boxes):
            if ch.isspace() or b.is_empty or b.is_infinite:
                continue
            key = (ch, round(b.x0, 1), round(b.y0, 1), round(b.x1, 1), round(b.y1, 1))
            index.setdefault(key, []).append(b)
    return index


def _moved(before: dict, after: dict, tol: float = 0.3) -> int:
    buckets: dict = {}
    for (ch, x0, y0, _x1, _y1) in before:
        buckets.setdefault((ch, int(round(y0))), []).append(x0)
    moved = 0
    for key in after:
        if key in before:
            continue
        ch, x0, y0 = key[0], key[1], int(round(key[2]))
        cands = buckets.get((ch, y0), []) + buckets.get((ch, y0 - 1), []) + buckets.get((ch, y0 + 1), [])
        if not any(abs(x0 - c) <= tol for c in cands):
            moved += 1
    return moved


def chars_inside(page, rects: Sequence, share: float = 0.5) -> int:
    count = 0
    for text, boxes in text_lines(page):
        for ch, b in zip(text, boxes):
            if ch.isspace() or b.is_empty:
                continue
            for r in rects:
                inter = b & r
                if not inter.is_empty and inter.get_area() > share * b.get_area():
                    count += 1
                    break
    return count


def _remove_interactive(page, rects: Sequence, everything: bool = False) -> int:
    def touches(r) -> bool:
        return everything or any(pymupdf.Rect(r).intersects(x) for x in rects)
    removed = 0
    annot = page.first_annot
    while annot:
        if annot.type[0] != pymupdf.PDF_ANNOT_REDACT and touches(annot.rect):
            annot = page.delete_annot(annot)
            removed += 1
        else:
            annot = annot.next
    widget = page.first_widget
    while widget:
        nxt = widget.next
        if touches(widget.rect):
            page.delete_widget(widget)
            removed += 1
        widget = nxt
    for link in page.get_links():
        if touches(link.get("from", pymupdf.Rect())):
            page.delete_link(link)
            removed += 1
    return removed


def _black_out(pix, rects: Sequence, clip, mat) -> None:
    for r in rects:
        if not r.intersects(clip):
            continue
        q = (r & clip) * mat
        ir = pymupdf.IRect(math.floor(q.x0) - 1, math.floor(q.y0) - 1,
                           math.ceil(q.x1) + 1, math.ceil(q.y1) + 1) & pix.irect
        if not ir.is_empty:
            pix.set_rect(ir, (0, 0, 0))


def _gap(a, b) -> float:
    dx = max(0.0, max(a.x0, b.x0) - min(a.x1, b.x1))
    dy = max(0.0, max(a.y0, b.y0) - min(a.y1, b.y1))
    return math.hypot(dx, dy)


def redact_page(page, rect_list: Sequence[tuple], dpi: int, vector_mode: int, force_flatten: bool = False) -> dict:
    """Removes content (not just covers it) and rasterises only the redacted regions.

    (1) annotations, form fields and links touching a region are deleted; (2) an
    untouched in-memory snapshot of the page is taken; (3) MuPDF removes overlapping
    text, blanks overlapping image pixels and removes vector drawings in the region;
    (4) the characters actually removed are measured, and an image patch rendered
    from the snapshot (every region blacked out in memory) restores the visible,
    non-redacted remainder; (5) if the page cannot be sanitised selectively (text
    left inside a region, or remaining text displaced) the whole page is flattened."""
    info = {"regions": 0, "flattened": False, "reason": ""}
    rotation = page.rotation
    if rotation:
        page.set_rotation(0)
    snapshot = None
    try:
        bounds = page.rect
        rects = [pymupdf.Rect(r) & bounds for r in rect_list]
        rects = [r for r in rects if not r.is_empty]
        if not rects:
            return info
        info["regions"] = len(rects)
        _remove_interactive(page, rects)
        snapshot = pymupdf.open()
        snapshot.insert_pdf(page.parent, from_page=page.number, to_page=page.number)
        snap_page = snapshot[0]
        mat = pymupdf.Matrix(dpi / 72.0, dpi / 72.0)
        if not force_flatten:
            before = _char_index(page)
            for r in rects:
                page.add_redact_annot(r, fill=(0, 0, 0))
            page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_PIXELS, graphics=vector_mode,
                                  text=pymupdf.PDF_REDACT_TEXT_REMOVE)
            after = _char_index(page)
            if _moved(before, after):
                info["reason"] = "remaining text was displaced by the redaction engine"
            elif chars_inside(page, rects):
                info["reason"] = "text could not be removed selectively from a region"
            else:
                patches = [pymupdf.Rect(r) for r in rects]
                for key, boxes in before.items():                 # neighbours MuPDF also removed
                    for b in boxes[len(after.get(key, [])):]:
                        if any(b in r for r in rects):
                            continue
                        i = min(range(len(rects)), key=lambda k: _gap(rects[k], b))
                        patches[i] |= b
                for p in patches:
                    p &= bounds
                    if p.is_empty:
                        continue
                    pix = snap_page.get_pixmap(matrix=mat, clip=p, alpha=False)
                    _black_out(pix, rects, p, mat)
                    page.insert_image(p, pixmap=pix, overlay=True, keep_proportion=False)
                    pix = None
                return info
        # Conservative fallback: flatten the whole page.
        info["flattened"] = True
        info["reason"] = info["reason"] or "full-page flattening requested"
        pix = snap_page.get_pixmap(matrix=mat, alpha=False)
        _black_out(pix, rects, bounds, mat)
        _remove_interactive(page, rects, everything=True)
        page.add_redact_annot(bounds, fill=(1, 1, 1))
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_REMOVE,
                              graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED,
                              text=pymupdf.PDF_REDACT_TEXT_REMOVE)
        page.insert_image(bounds, pixmap=pix, overlay=True, keep_proportion=False)
        pix = None
        return info
    finally:
        if snapshot is not None:
            snapshot.close()
        if rotation:
            page.set_rotation(rotation)


def _sanitise(doc) -> list[str]:
    try:
        doc.scrub(attached_files=True, clean_pages=False, embedded_files=True, hidden_text=False,
                  javascript=True, metadata=True, redactions=False, redact_images=0,
                  remove_links=False, reset_fields=False, reset_responses=True, thumbnails=True,
                  xml_metadata=True)
        return ["metadata, XMP, JavaScript, attachments, embedded files and thumbnails removed"]
    except Exception:
        doc.set_metadata({})
        try:
            doc.del_xml_metadata()
        except Exception:
            pass
        return ["metadata removed (full scrub unavailable in this PyMuPDF)"]


VECTOR_MODES = {"Remove drawings fully inside a region": pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED,
                "Remove drawings touching a region": pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED}


def apply(job: Job, src_path, password: str, regions: dict, out_path, dpi: int = 300,
          vector: str = "Remove drawings fully inside a region", sanitise: bool = True, flatten_all: bool = False,
          terms: Optional[list[str]] = None, approved: int = 0, ocr_verify: bool = True,
          ocr_lang: str = "eng") -> dict:
    """regions: {page index: [rect tuple, ...]} (unrotated page space)."""
    terms = terms or []
    regions = {int(k): v for k, v in regions.items()}
    if same_path(src_path, out_path):
        raise UserError("The redacted output must be a new file - the original is never overwritten.")
    if not engine_ok():
        raise UserError(ENGINE_ERROR.format(pymupdf_version()))
    if not regions:
        raise UserError("There are no approved regions to apply.")
    doc = open_pdf(src_path, password)
    source_pages = doc.page_count
    was_encrypted = bool(doc.is_encrypted or doc.needs_pass or (doc.metadata or {}).get("encryption"))
    flattened, applied, notes = [], 0, []
    toc_changed = 0
    try:
        pages = sorted(regions)
        total = len(pages) + 3
        for i, pno in enumerate(pages):
            job.step(i, total, f"Redacting page {pno + 1} ({i + 1} of {len(pages)})")
            info = redact_page(doc[pno], regions[pno], dpi, VECTOR_MODES.get(vector, 2), flatten_all)
            applied += info["regions"]
            if info["flattened"]:
                flattened.append((pno + 1, info["reason"]))
        job.step(len(pages), total, "Cleaning the document")
        norm_terms = [normalise(t) for t in terms if len(normalise(t)) >= 3]
        if norm_terms:
            toc = doc.get_toc(simple=False)
            for entry in toc:
                if any(t in normalise(entry[1]) for t in norm_terms):
                    entry[1] = "[REDACTED]"
                    toc_changed += 1
            if toc_changed:
                doc.set_toc(toc)
        if sanitise:
            notes += _sanitise(doc)
        job.step(len(pages) + 1, total, "Writing new PDF (full rewrite, no incremental update)")
        save_pdf(doc, out_path, garbage=3, deflate=True, clean=True, encryption=pymupdf.PDF_ENCRYPT_NONE)
    finally:
        doc.close()
    job.step(len(regions) + 2, len(regions) + 3, "Verifying the redacted file")
    checks = verify_output(job, out_path, source_pages, regions, terms, sanitise, ocr_verify, ocr_lang)
    failed = any(c[0] == "FAIL" for c in checks)
    return {"out": str(out_path), "pages_processed": len(regions), "regions": applied, "approved": approved,
            "flattened": flattened, "toc_changed": toc_changed, "notes": notes,
            "was_encrypted": was_encrypted, "checks": checks, "failed": failed}


# ================================================================== verification

def _dark_share(page, rect) -> float:
    """Share of near-black pixels inside rect (unrotated space), rendered at 72 dpi."""
    r = pymupdf.Rect(rect)
    inner = pymupdf.Rect(r.x0 + 1, r.y0 + 1, r.x1 - 1, r.y1 - 1)
    if inner.is_empty or inner.width < 1 or inner.height < 1:
        return 1.0
    rot = page.rotation
    if rot:
        page.set_rotation(0)                          # in memory only - the file is not saved
    try:
        pix = page.get_pixmap(clip=inner, dpi=72, alpha=False, colorspace=pymupdf.csGRAY)
    finally:
        if rot:
            page.set_rotation(rot)
    data = pix.samples
    if not data:
        return 1.0
    return sum(1 for b in data if b < 70) / len(data)


def _ocr_hits(job: Job, doc, norm_terms: list[str], lang: str, pages: Optional[list[int]] = None) -> dict:
    """Terms readable by OCR on image-only pages: {term: [page numbers]}."""
    hits: dict[str, list[int]] = {}
    pages = pages if pages is not None else list(range(doc.page_count))
    for i, pno in enumerate(pages):
        page = doc[pno]
        if page.get_text("text").strip():
            continue
        job.progress(i, len(pages), f"Reading scanned page {pno + 1} with OCR to check for leaks")
        text = normalise(" ".join(t for t, _b in ocr_lines(page, lang)))
        for t in norm_terms:
            if t in text:
                hits.setdefault(t, []).append(pno + 1)
    return hits


def verify_output(job: Job, path, expected_pages: int, regions: dict, terms: list[str], sanitised: bool,
                  ocr_verify: bool = True, ocr_lang: str = "eng") -> list[tuple[str, str, str]]:
    """Re-open the saved file and run post-redaction checks: (status, check, detail)."""
    checks: list[tuple[str, str, str]] = []
    try:
        doc = pymupdf.open(str(path))
    except Exception as exc:
        return [("FAIL", "Output opens", f"Could not reopen the output: {exc}")]
    try:
        checks.append(("PASS", "Output opens", "The redacted PDF reopens without errors."))
        checks.append(("PASS" if doc.page_count == expected_pages else "FAIL", "Page count",
                       f"{doc.page_count} page(s), source had {expected_pages}."))
        leaks, annots_left, not_black = [], 0, []
        for pno, rects in regions.items():
            page = doc[int(pno)]
            rr = [pymupdf.Rect(r) for r in rects]
            if chars_inside(page, rr):
                leaks.append(int(pno) + 1)
            for annot in page.annots():
                if any(annot.rect.intersects(r) for r in rr):
                    annots_left += 1
            for w in page.widgets():
                if any(w.rect.intersects(r) for r in rr):
                    annots_left += 1
            if any(_dark_share(page, r) < 0.9 for r in rr):
                not_black.append(int(pno) + 1)
        checks.append(("FAIL" if leaks else "PASS", "Text inside redacted regions",
                       f"Extractable text remains on page(s) {', '.join(map(str, leaks))}." if leaks
                       else "No extractable text remains inside any redacted region."))
        checks.append(("FAIL" if not_black else "PASS", "Redacted areas blacked out",
                       f"Visible content remains in a redacted area on page(s) {', '.join(map(str, not_black))}."
                       if not_black else "Every redacted area is solid black in the saved file."))
        checks.append(("FAIL" if annots_left else "PASS", "Annotations / form fields in regions",
                       f"{annots_left} remain." if annots_left else "None remain in redacted regions."))
        norm_terms = sorted({normalise(t) for t in terms if len(normalise(t)) >= 3})
        if norm_terms:
            elsewhere: dict[str, list[int]] = {}
            for pno in range(doc.page_count):
                page_text = normalise(doc[pno].get_text("text"))
                for t in norm_terms:
                    if t in page_text:
                        elsewhere.setdefault(t, []).append(pno + 1)
            if elsewhere:
                detail = "; ".join(f"{mask_value(t)} on p.{','.join(map(str, p[:10]))}"
                                   for t, p in sorted(elsewhere.items()))
                checks.append(("WARN", "Redacted values elsewhere in the text",
                               "Still present outside the approved regions (not selected for redaction): " + detail))
            else:
                checks.append(("PASS", "Redacted values in document text",
                               f"None of the {len(norm_terms)} targeted value(s) can be extracted anywhere."))
            meta_text = normalise(" ".join(str(v) for v in (doc.metadata or {}).values() if v))
            toc_text = normalise(" ".join(t[1] for t in doc.get_toc(simple=True)))
            found = [mask_value(t) for t in norm_terms if t in meta_text or t in toc_text]
            checks.append(("FAIL" if found else "PASS", "Metadata and bookmarks",
                           f"Targeted values found: {', '.join(found)}" if found
                           else "No targeted values in metadata or bookmarks."))
        else:
            checks.append(("INFO", "Targeted values", "Manual regions only - no text values to search for."))
        checks.extend(structure_checks(doc, path, sanitised))
        image_pages = [p for p in range(doc.page_count) if not doc[p].get_text("text").strip()]
        if not image_pages:
            checks.append(("PASS", "Scanned pages", "Every page has a text layer - nothing is held only as pixels."))
        elif not norm_terms:
            checks.append(("INFO", "Scanned pages", f"{len(image_pages)} image-only page(s); no text values to "
                                                    "look for with OCR."))
        elif not ocr_verify:
            checks.append(("NOT CHECKED", "Values inside scanned pages",
                           "OCR verification was switched off; text held only as pixels was not read."))
        else:
            try:
                hits = _ocr_hits(job, doc, norm_terms, ocr_lang, image_pages)
                if hits:
                    detail = "; ".join(f"{mask_value(t)} on p.{','.join(map(str, p[:10]))}"
                                       for t, p in sorted(hits.items()))
                    checks.append(("WARN", "Values readable on scanned pages (OCR)",
                                   "Still readable outside the redacted areas: " + detail))
                else:
                    checks.append(("PASS", "Values readable on scanned pages (OCR)",
                                   f"OCR of {len(image_pages)} scanned page(s) finds none of the targeted values."))
            except ocr.OcrError as exc:
                checks.append(("NOT CHECKED", "Values inside scanned pages", f"OCR not available: {exc}"))
    finally:
        doc.close()
    return checks


def structure_checks(doc, path, expect_clean: bool) -> list[tuple[str, str, str]]:
    checks: list[tuple[str, str, str]] = []
    try:
        with open(path, "rb") as fh:
            eof = fh.read().count(b"%%EOF")
        checks.append(("PASS" if eof <= 1 else "WARN", "Incremental revisions",
                       "Single revision (full rewrite)." if eof <= 1 else
                       f"{eof} revisions found - earlier versions may be recoverable."))
    except OSError as exc:
        checks.append(("NOT CHECKED", "Incremental revisions", str(exc)))
    js = 0
    for xref in range(1, doc.xref_length()):
        try:
            obj = doc.xref_object(xref, compressed=False)
        except Exception:
            continue
        if "/JavaScript" in obj or re.search(r"/JS[\s(<\[]", obj):
            js += 1
    checks.append(("WARN" if js else "PASS", "JavaScript", f"{js} JavaScript object(s)." if js else "None found."))
    emb = doc.embfile_count()
    checks.append(("WARN" if emb else "PASS", "Embedded files", f"{emb} embedded file(s)." if emb else "None."))
    meta = {k: v for k, v in (doc.metadata or {}).items() if v and k not in ("format", "encryption")}
    if expect_clean:
        checks.append(("WARN" if meta else "PASS", "Document metadata",
                       f"Remaining: {', '.join(meta)}" if meta else "Cleared."))
    else:
        checks.append(("INFO", "Document metadata", f"Kept (clean-up not selected): {', '.join(meta) or 'none'}"))
    try:
        ocgs = doc.get_ocgs()
        if ocgs:
            checks.append(("INFO", "Optional content layers",
                           f"{len(ocgs)} layer(s). Text in hidden layers inside regions is removed too."))
    except Exception:
        pass
    return checks


def inspect(job: Job, path, password: str, terms: list[str], ocr_verify: bool = True,
            ocr_lang: str = "eng") -> dict:
    """Stand-alone verification of any PDF (Verify Redacted PDF tool)."""
    doc = open_pdf(path, password)
    checks: list[tuple[str, str, str]] = [("PASS", "Opens", f"{doc.page_count} page(s).")]
    try:
        norm = [(t, normalise(t)) for t in terms if len(normalise(t)) >= 3]
        hits: dict[str, list[int]] = {}
        text_pages = annots = 0
        image_pages = []
        for pno in range(doc.page_count):
            job.step(pno, doc.page_count, f"Checking page {pno + 1}")
            page = doc[pno]
            raw = page.get_text("text")
            if raw.strip():
                text_pages += 1
            else:
                image_pages.append(pno)
            low = normalise(raw)
            for t, n in norm:
                if n in low:
                    hits.setdefault(t, []).append(pno + 1)
            for a in page.annots():
                annots += 1
                info = normalise(a.info.get("content", "") + a.info.get("title", ""))
                for t, n in norm:
                    if n in info:
                        hits.setdefault(t + " (annotation)", []).append(pno + 1)
        ocr_note, ocr_ran = "", False
        if norm and image_pages and ocr_verify:
            try:
                for n, pages in _ocr_hits(job, doc, [n for _t, n in norm], ocr_lang, image_pages).items():
                    t = next(t for t, nn in norm if nn == n)
                    hits.setdefault(t + " (scanned page, OCR)", []).extend(pages)
                ocr_note, ocr_ran = f"{len(image_pages)} scanned page(s) also read with OCR.", True
            except ocr.OcrError as exc:
                ocr_note = f"Scanned pages not read - OCR not available: {exc}"
        for t, _n in norm:
            found = sorted(k for k in hits if k.startswith(t))
            if found:
                checks.append(("FOUND", f"Term {mask_value(t)}",
                               "; ".join("%s on page(s) %s" % ("annotation" if "(annotation)" in k else
                                                               "scanned page (OCR)" if "OCR" in k else "text",
                                                               ", ".join(map(str, hits[k][:15]))) for k in found)))
            else:
                checks.append(("ABSENT", f"Term {mask_value(t)}", "Not found in text, annotations"
                               + (" or scanned pages (OCR)." if ocr_ran else ".")))
        meta_text = normalise(" ".join(str(v) for v in (doc.metadata or {}).values() if v))
        toc_text = normalise(" ".join(t[1] for t in doc.get_toc(simple=True)))
        for t, n in norm:
            if n in meta_text or n in toc_text:
                checks.append(("FOUND", f"Term {mask_value(t)}", "Present in metadata or bookmarks."))
        checks.append(("INFO", "Annotations", f"{annots} annotation(s) in the document."))
        checks.append(("INFO", "Text layer", f"{text_pages} of {doc.page_count} page(s) contain extractable text."))
        checks.extend(structure_checks(doc, path, expect_clean=True))
        if image_pages:
            if not norm:
                checks.append(("INFO", "Scanned pages", f"{len(image_pages)} image-only page(s); enter values to "
                                                        "look for them with OCR."))
            elif ocr_note:
                checks.append(("INFO" if "not available" not in ocr_note else "NOT CHECKED", "Scanned pages",
                               ocr_note))
            else:
                checks.append(("NOT CHECKED", "Scanned pages", "OCR was switched off; text held only as pixels "
                                                               "was not read."))
    finally:
        doc.close()
    return {"path": str(path), "checks": checks}
