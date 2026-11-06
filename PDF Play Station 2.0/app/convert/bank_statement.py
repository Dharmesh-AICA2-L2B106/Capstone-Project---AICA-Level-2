"""Bank-statement mode: column-aware extraction with running-balance verification.

Bank statements have a property ordinary documents lack: every row must
satisfy  previous balance - withdrawal + deposit = balance.  This module uses
that rule to find and repair OCR errors instead of trusting the OCR blindly.

Pipeline (per page, entirely offline):

1. Words: from the PDF text layer when present, otherwise from Tesseract OCR
   of the page image (300 dpi). All coordinates are in 300-dpi pixels.
2. Columns: the header line containing Withdrawal/Debit, Deposit/Credit and
   Balance defines the column bands. A page can contain several headers
   (statements printed as several "pages" per sheet).
3. Rows: each balance amount is a row anchor. Date/particulars lines are
   aligned to anchors by a sequence alignment that tolerates a constant
   vertical offset (some core-banking printouts print the amounts half a line
   above their description) and missed lines.
4. Verification: each row is checked against the running balance. Failing
   cells are re-read from the image with digit-only OCR; if a re-read value
   satisfies the balance it is used ("Re-read"). Otherwise the amount (or
   balance) is computed from the neighbouring balances only when that makes
   the following row consistent too ("Inferred"). Anything else is flagged
   "Check". Nothing is changed silently: the raw OCR text is kept for every
   row and every corrected value is labelled.
5. Totals: lines such as "Cumulative Totals" / "Total" are captured as
   checkpoints and compared with the computed totals.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from statistics import median
from typing import Callable, Optional

import pypdfium2 as pdfium

from .ocr_engine import OcrEngine, OcrError
from .pdf_inspector import PDFIUM_LOCK

log = logging.getLogger(__name__)

DPI = 300
REREAD_DPI = 400
PT = DPI / 72.0

# An amount: 1-3 leading digits (not a lone leading zero before a comma group),
# comma groups, and exactly two decimals.
_AMOUNT = re.compile(r"(?<![\d,])((?:[1-9]\d{0,2})(?:,\d{2,3})+|\d+)\.(\d{2})(?!\d)")
_DATE = re.compile(r"^(\d{1,2})[-/.](\d{1,2}|[A-Za-z]{3})[-/.](\d{2,4})")
_DATE_SPACED = re.compile(r"^(\d{1,2}) ([A-Za-z]{3}) (\d{2,4})")
_BF = re.compile(r"\b(B/?F|BROUGHT\s+FORWARD|OPENING\s+BAL(ANCE)?)\b", re.I)
_TOTAL = re.compile(r"\b(CUMULATIVE\s+TOTALS?|TOTALS?|PAGE\s+TOTAL|GRAND\s+TOTAL)\b", re.I)
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}

# Matched against the word with everything but letters removed, so OCR noise
# such as 'DEPOSITS.' or 'BALANCE’' still matches.
_HEAD = {
    "withdrawal": re.compile(r"^(WITHDRAWAL\w*|DEBIT\w*|DR)$"),
    "deposit": re.compile(r"^(DEPOSIT\w*|CREDIT\w*|CR)$"),
    "balance": re.compile(r"^(BALANCE\w*|BAL)$"),
    "cheque": re.compile(r"^(CHQ\w*|CHEQUE\w*|REFNO)$"),
}

ProgressFn = Callable[[str, int, int], None]   # (message, pages done, total pages)


class StatementError(Exception):
    """The document does not look like a supported bank statement."""


@dataclass
class SWord:
    text: str
    x0: float
    x1: float
    top: float
    bottom: float
    conf: float = 100.0

    @property
    def xc(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def yc(self) -> float:
        return (self.top + self.bottom) / 2


@dataclass
class Columns:
    text_right: float      # date + particulars are left of this
    cheque: Optional[tuple[float, float]]
    w_left: float
    wd: float              # boundary withdrawal | deposit
    db: float              # boundary deposit | balance
    top: float             # y below the header line
    bottom: float          # y where the section ends


@dataclass
class StatementRow:
    page: int
    y: float
    kind: str = "txn"                        # txn | bf
    date_text: str = ""
    particulars: str = ""
    details: list[str] = field(default_factory=list)
    cheque: str = ""
    withdrawal: Optional[Decimal] = None
    deposit: Optional[Decimal] = None
    balance: Optional[Decimal] = None
    raw: dict = field(default_factory=dict)  # raw OCR text per column
    status: str = "OK"                       # OK | Re-read | Corrected | Inferred | Check
    notes: list[str] = field(default_factory=list)
    boxes: dict = field(default_factory=dict)  # column -> (x0, y0, x1, y1) in px for re-reading

    @property
    def date(self) -> Optional[datetime]:
        return parse_statement_date(self.date_text)


@dataclass
class Checkpoint:
    page: int
    after_row: int                 # index into rows (inclusive)
    label: str
    withdrawals: Optional[Decimal]
    deposits: Optional[Decimal]
    balance: Optional[Decimal]
    computed: tuple = ()
    matches: Optional[bool] = None


@dataclass
class StatementResult:
    source: Path
    rows: list[StatementRow] = field(default_factory=list)
    checkpoints: list[Checkpoint] = field(default_factory=list)
    header_text: list[str] = field(default_factory=list)
    pages_used: list[int] = field(default_factory=list)
    method: str = "ocr"            # ocr | text
    warnings: list[str] = field(default_factory=list)

    def count(self, status: str) -> int:
        return sum(1 for r in self.rows if r.status == status)

    @property
    def fully_reconciled(self) -> bool:
        return self.rows != [] and self.count("Check") == 0 and \
            all(c.matches is not False for c in self.checkpoints)


# ---------------------------------------------------------------- parsing helpers

def parse_amount(text: str, last: bool = False) -> Optional[Decimal]:
    """First (or last) well-formed amount in the text."""
    s = text.replace("O", "0").replace("o", "0")
    # OCR sometimes splits one number ('2,49, 641.16'); rejoin only inside numbers,
    # so two neighbouring amounts ('20,000.00 1,69,740.16') stay separate.
    s = re.sub(r"(?<=\d),\s+(?=\d)", ",", s)
    s = re.sub(r"(?<=\d)\s+(?=[.,]\d)|(?<=\d[.,])\s+(?=\d)", "", s)
    matches = list(_AMOUNT.finditer(s))
    if not matches:
        return None
    m = matches[-1] if last else matches[0]
    try:
        return Decimal(m.group(1).replace(",", "") + "." + m.group(2))
    except InvalidOperation:
        return None


def parse_balance(text: str) -> Optional[Decimal]:
    # The balance is the right-most amount: a long deposit can spill into the strip.
    value = parse_amount(text, last=True)
    if value is None:
        return None
    tail = text.replace(" ", "")[-3:].upper()
    if "DR" in tail or tail.endswith("D"):
        return -value
    if text.strip().startswith("-"):
        return -value
    return value


def parse_statement_date(text: str) -> Optional[datetime]:
    m = _DATE.match(text) or _DATE_SPACED.match(text)
    if not m:
        return None
    d, mo, y = m.groups()
    try:
        month = int(mo) if mo.isdigit() else _MONTHS[mo.lower()]
        year = int(y) + (2000 if len(y) == 2 else 0)
        return datetime(year, month, int(d))
    except (KeyError, ValueError):
        return None


def _starts_with_date(text: str) -> bool:
    return bool(_DATE.match(text) or _DATE_SPACED.match(text))


def _norm_head(text: str) -> str:
    return re.sub(r"[^A-Z]", "", text.upper())


# ---------------------------------------------------------------- words

def _ocr_words(engine: OcrEngine, image, lang: str, timeout: int) -> list[SWord]:
    return [SWord(w.text, w.left, w.left + w.width, w.top, w.top + w.height, w.conf)
            for w in engine.recognise(image, lang, timeout=timeout, psm=6)]


def _strip_words(engine: OcrEngine, image, cols: "Columns", timeout: int) -> dict[str, list[SWord]]:
    """OCR each amount column as a narrow strip, digits only.

    Full-page OCR sometimes drops short numbers that stand alone in a wide,
    mostly empty column (e.g. '17.70'). Reading the column strip on its own
    is far more reliable for amounts; handwriting in the strip turns into
    digit noise that the strict amount pattern later rejects."""
    # One crop over all amount columns, assigned to columns by each number's
    # CENTRE: cutting strips at a boundary can slice the first digit off a long
    # balance that starts close to the deposit column.
    out: dict[str, list[SWord]] = {"w": [], "d": [], "b": [], "t": []}
    top, bottom = int(cols.top), int(min(cols.bottom, image.height))
    if bottom - top < 20:
        return out
    margin = 0.5 * (cols.wd - cols.w_left)
    box = (max(0, int(cols.w_left - margin)), top, image.width, bottom)
    for w in engine.recognise(image.crop(box), "eng", timeout=timeout, psm=6, whitelist="0123456789,.CrD"):
        word = SWord(w.text, w.left + box[0], w.left + w.width + box[0], w.top + top, w.top + w.height + top, w.conf)
        if word.xc >= cols.db:
            out["b"].append(word)
        elif word.xc >= cols.wd:
            out["d"].append(word)
        elif word.xc >= cols.w_left:
            out["w"].append(word)
    # Date and particulars as their own strip: whole-page OCR skips some lines of
    # small print when a busy amounts area sits beside them.
    tbox = (0, top, int(cols.cheque[1] if cols.cheque else cols.w_left), bottom)
    for w in engine.recognise(image.crop(tbox), "eng", timeout=timeout, psm=6):
        out["t"].append(SWord(w.text, w.left, w.left + w.width, w.top + top, w.top + w.height + top, w.conf))
    return out


def _text_words(plumber_page) -> list[SWord]:
    words = plumber_page.extract_words(x_tolerance=1.5, y_tolerance=2.5, keep_blank_chars=False)
    return [SWord(w["text"], w["x0"] * PT, w["x1"] * PT, w["top"] * PT, w["bottom"] * PT) for w in words]


def _group_lines(words: list[SWord], tol: float) -> list[list[SWord]]:
    lines: list[list[SWord]] = []
    for w in sorted(words, key=lambda w: w.yc):
        if lines and abs(w.yc - median(x.yc for x in lines[-1])) <= tol:
            lines[-1].append(w)
        else:
            lines.append([w])
    return [sorted(l, key=lambda w: w.x0) for l in lines]


def _line_y(line: list[SWord]) -> float:
    return median(w.yc for w in line)


# ---------------------------------------------------------------- columns

def find_sections(words: list[SWord], page_height: float) -> list[Columns]:
    """Locate header lines (Withdrawal/Deposit/Balance) and derive column bands."""
    heights = [w.bottom - w.top for w in words if w.text.strip()]
    tol = (median(heights) if heights else 30) * 0.7
    headers: list[dict] = []
    for line in _group_lines(words, tol):
        found: dict[str, SWord] = {}
        for w in line:
            t = _norm_head(w.text)
            for key, rx in _HEAD.items():
                if key not in found and rx.match(t):
                    found[key] = w
        if {"withdrawal", "deposit", "balance"} <= found.keys():
            wx, dx, bx = found["withdrawal"], found["deposit"], found["balance"]
            if wx.xc < dx.xc < bx.xc:
                found["y"] = max(w.bottom for w in line)
                headers.append(found)
    sections = []
    for i, h in enumerate(headers):
        wx, dx, bx = h["withdrawal"], h["deposit"], h["balance"]
        width = wx.x1 - wx.x0
        chq = h.get("cheque")
        w_left = (chq.x1 + wx.x0) / 2 if chq else wx.x0 - 0.6 * width
        text_right = chq.x0 - 0.3 * width if chq else w_left
        bottom = headers[i + 1]["y"] - 80 if i + 1 < len(headers) else page_height
        # Amounts are right-aligned under their headings, so a long value starts
        # well to the left of its heading. The boundary between two amount
        # columns is therefore placed just after the left column's heading.
        sections.append(Columns(text_right=text_right, cheque=(text_right, w_left) if chq else None,
                                w_left=w_left, wd=wx.x1 + 0.35 * (dx.x0 - wx.x1),
                                db=dx.x1 + 0.3 * (bx.x0 - dx.x1), top=h["y"] + 5, bottom=bottom))
    return sections


# ---------------------------------------------------------------- rows

@dataclass
class _Anchor:
    y: float
    w_text: str
    d_text: str
    b_text: str
    words: list[SWord]


@dataclass
class _TextLine:
    y: float
    text: str
    kind: str          # date | bf | total | detail
    cheque: str = ""


def _align(anchors: list[_Anchor], lines: list[_TextLine], pitch: float
           ) -> tuple[list[tuple[Optional[int], Optional[int]]], float]:
    """Sequence-align anchors with date/bf/total lines allowing a constant offset.
    Returns (pairs, offset) where offset = typical (text line y - amount y)."""
    keys = [i for i, l in enumerate(lines) if l.kind != "detail"]
    best: tuple[float, list, float] = (float("inf"), [], 0.0)
    n, m = len(anchors), len(keys)
    gap = 0.9
    for step in range(-9, 10):
        off = step * 0.1 * pitch
        cost = [[0.0] * (m + 1) for _ in range(n + 1)]
        back = [[0] * (m + 1) for _ in range(n + 1)]
        for i in range(1, n + 1):
            cost[i][0], back[i][0] = i * gap, 1
        for j in range(1, m + 1):
            cost[0][j], back[0][j] = j * gap, 2
        for i in range(1, n + 1):
            for j in range(1, m + 1):
                dy = abs(lines[keys[j - 1]].y - anchors[i - 1].y - off) / pitch
                match = cost[i - 1][j - 1] + (dy if dy < 0.75 else 5.0)
                skip_a = cost[i - 1][j] + gap
                skip_l = cost[i][j - 1] + gap
                cost[i][j], back[i][j] = min((match, 0), (skip_a, 1), (skip_l, 2))
        if cost[n][m] < best[0]:
            pairs = []
            i, j = n, m
            while i or j:
                b = back[i][j]
                if b == 0:
                    pairs.append((i - 1, keys[j - 1])); i -= 1; j -= 1
                elif b == 1:
                    pairs.append((i - 1, None)); i -= 1
                else:
                    pairs.append((None, keys[j - 1])); j -= 1
            best = (cost[n][m], list(reversed(pairs)), off)
    return best[1], best[2]


def rows_from_section(words: list[SWord], cols: Columns, page: int,
                      rows: list[StatementRow], checkpoints: list[Checkpoint],
                      amount_words: Optional[dict[str, list[SWord]]] = None) -> None:
    sec = [w for w in words if cols.top <= w.yc < cols.bottom]
    if not sec:
        return
    heights = sorted(w.bottom - w.top for w in sec)
    tol = heights[len(heights) // 2] * 0.55

    def region(w: SWord) -> str:
        if w.xc >= cols.db:
            return "b"
        if w.xc >= cols.wd:
            return "d"
        if w.xc >= cols.w_left:
            return "w"
        if cols.cheque and w.xc >= cols.cheque[0]:
            return "c"
        return "t"

    by = {k: [w for w in sec if region(w) == k] for k in "bdwct"}
    for key, strip in (amount_words or {}).items():
        if strip:
            by[key] = [w for w in strip if cols.top <= w.yc < cols.bottom]
    if amount_words and amount_words.get("t") and cols.cheque:
        text_words = by["t"]
        by["t"] = [w for w in text_words if w.xc < cols.cheque[0]]
        by["c"] = [w for w in text_words if w.xc >= cols.cheque[0]]
    anchors: list[_Anchor] = []
    for line in _group_lines(by["b"], tol):
        text = " ".join(w.text for w in line)
        if parse_amount(text) is None:
            continue
        anchors.append(_Anchor(_line_y(line), "", "", text, line))
    if not anchors:
        return
    ys = [a.y for a in anchors]
    diffs = sorted(b - a for a, b in zip(ys, ys[1:]) if b - a > tol)
    pitch = diffs[len(diffs) // 2] if diffs else 60.0
    amount_lines: dict[str, list[tuple[float, str]]] = {"w": [], "d": []}
    for key in ("w", "d"):
        for line in _group_lines(by[key], tol):
            text = " ".join(w.text for w in line)
            if parse_amount(text) is None:
                continue
            y = _line_y(line)
            amount_lines[key].append((y, text))
            a = min(anchors, key=lambda a: abs(a.y - y))
            if abs(a.y - y) <= 0.45 * pitch:
                setattr(a, f"{key}_text", (getattr(a, f"{key}_text") + " " + text).strip())

    lines: list[_TextLine] = []
    cheques = _group_lines(by["c"], tol)
    for line in _group_lines(by["t"], tol):
        text = " ".join(w.text for w in line).strip(" ,'`")
        text = re.sub(r"^[^\w/]+", "", text)
        if len(re.sub(r"[^A-Za-z0-9]", "", text)) < 3 and not _BF.search(text):
            continue          # tick marks / specks read as single letters
        y = _line_y(line)
        kind = "date" if _starts_with_date(text) else "bf" if _BF.search(text) else \
            "total" if _TOTAL.search(text) else "detail"
        chq = ""
        for cl in cheques:
            if abs(_line_y(cl) - y) <= 0.45 * pitch:
                chq = "".join(w.text for w in cl)
        lines.append(_TextLine(y, text, kind, chq))

    # Keep only the table body: nothing far above the first amount, and nothing
    # after the totals line (report date, server ids, the next page's banner).
    first_y = min(a.y for a in anchors) - 1.5 * pitch
    totals = [l.y for l in lines if l.kind == "total"]
    last_y = (max(totals) + 0.3 * pitch) if totals else max(a.y for a in anchors) + 1.5 * pitch
    lines = [l for l in lines if first_y <= l.y <= last_y or (l.kind == "detail" and first_y <= l.y)]
    if totals:
        lines = [l for l in lines if l.y <= last_y]

    pairs, offset = _align(anchors, lines, pitch)
    section_rows: list[tuple[float, StatementRow]] = []
    for ai, li in pairs:
        a = anchors[ai] if ai is not None else None
        line = lines[li] if li is not None else None
        if line is not None and line.kind == "total":
            after = len(rows) + len(section_rows) - 1
            if a is not None:
                checkpoints.append(Checkpoint(page, after, line.text, parse_amount(a.w_text),
                                              parse_amount(a.d_text), parse_balance(a.b_text)))
            else:
                # balance unreadable: keep the printed withdrawal/deposit totals
                ay = line.y - offset
                near = lambda key: next((parse_amount(t) for y, t in amount_lines[key]
                                         if abs(y - ay) <= 0.45 * pitch), None)
                w_tot, d_tot = near("w"), near("d")
                if w_tot is not None or d_tot is not None:
                    checkpoints.append(Checkpoint(page, after, line.text, w_tot, d_tot, None))
            continue
        if line is None and a is not None:
            # A balance with no text line that repeats the previous balance is an
            # unlabelled totals line (e.g. 'Cumulative Totals' not recognised).
            prev_rows = [r for _, r in section_rows] or rows
            prev_b = prev_rows[-1].balance if prev_rows else None
            both = parse_amount(a.w_text) is not None and parse_amount(a.d_text) is not None
            if both or (prev_b is not None and parse_balance(a.b_text) == prev_b):
                # Withdrawal AND deposit on one unlabelled line: a totals line
                # (a transaction is never both).
                checkpoints.append(Checkpoint(page, len(rows) + len(section_rows) - 1, "Totals",
                                              parse_amount(a.w_text), parse_amount(a.d_text),
                                              parse_balance(a.b_text)))
                continue
        row = StatementRow(page=page, y=a.y if a else line.y)
        if line is not None:
            row.kind = "bf" if line.kind == "bf" else "txn"
            if line.kind == "date":
                m = _DATE.match(line.text) or _DATE_SPACED.match(line.text)
                row.date_text = line.text[:m.end()]
                row.particulars = line.text[m.end():].strip()
            else:
                row.particulars = line.text
            row.cheque = line.cheque
            row.raw["text"] = line.text
            row.boxes["t"] = (0, line.y - 0.5 * pitch, cols.text_right, line.y + 0.5 * pitch)
        else:
            row.notes.append("No date/particulars line found for this balance.")
        if a is not None:
            row.withdrawal = parse_amount(a.w_text)
            row.deposit = parse_amount(a.d_text)
            row.balance = parse_balance(a.b_text)
            row.raw.update(w=a.w_text, d=a.d_text, b=a.b_text)
            y0, y1 = min(w.top for w in a.words), max(w.bottom for w in a.words)
            pad = 0.25 * pitch
            row.boxes.update({"w": (cols.w_left, y0 - pad, cols.wd, y1 + pad),
                              "d": (cols.wd, y0 - pad, cols.db, y1 + pad),
                              "b": (cols.db, y0 - pad, None, y1 + pad)})
            if "t" not in row.boxes:     # where its description line should be
                ty = a.y + offset
                row.boxes["t"] = (0, ty - 0.5 * pitch, cols.text_right, ty + 0.5 * pitch)
        else:
            if line is not None and _starts_with_date(line.text) and len(line.text) <= 11:
                continue          # a bare date with no amounts: report footer, not a transaction
            row.notes.append("No balance was read for this line.")
            ay = line.y - offset
            row.boxes.update({"w": (cols.w_left, ay - 0.45 * pitch, cols.wd, ay + 0.45 * pitch),
                              "d": (cols.wd, ay - 0.45 * pitch, cols.db, ay + 0.45 * pitch),
                              "b": (cols.db, ay - 0.45 * pitch, None, ay + 0.45 * pitch)})
        section_rows.append((row.y, row))
    # continuation lines (extra narration under a transaction)
    for line in lines:
        if line.kind != "detail":
            continue
        owner = None
        for y, r in section_rows:
            ref = y if not r.raw.get("text") else next((l.y for l in lines if l.text == r.raw["text"]), y)
            if ref < line.y:
                owner = r
        if owner is not None and line.y - owner.y < 12 * pitch:
            owner.details.append(line.text)
    rows.extend(r for _, r in section_rows)


# ---------------------------------------------------------------- verification

def _balanced(prev: Optional[Decimal], w: Optional[Decimal], d: Optional[Decimal], b: Optional[Decimal]) -> bool:
    """A transaction balances only if it HAS an amount and the arithmetic holds.
    (Without the amount requirement, a balance that lost a digit could
    'balance' against an equally wrong previous balance.)"""
    if prev is None or b is None or (not w and not d):
        return False
    return prev - (w or 0) + (d or 0) == b


class _Rereader:
    """Re-reads single cells with digit-only OCR at a higher resolution."""

    def __init__(self, doc: Optional[pdfium.PdfDocument], engine: Optional[OcrEngine], lang: str):
        self.doc, self.engine, self.lang = doc, engine, lang
        self.cache: dict[int, object] = {}

    def _image(self, page: int):
        if page not in self.cache:
            with PDFIUM_LOCK:
                p = self.doc[page - 1]
                try:
                    self.cache = {page: p.render(scale=REREAD_DPI / 72).to_pil().convert("L")}
                finally:
                    p.close()
        return self.cache[page]

    def text_lines(self, row: StatementRow) -> list[str]:
        """Re-read the date/particulars line of a row (several OCR passes)."""
        if self.doc is None or self.engine is None or "t" not in row.boxes:
            return []
        img = self._image(row.page)
        x0, y0, x1, y1 = row.boxes["t"]
        f = REREAD_DPI / DPI
        crop = img.crop((int(x0 * f), max(0, int(y0 * f)), int(x1 * f), min(img.height, int(y1 * f))))
        out = []
        for psm, wl in ((7, ""), (6, ""), (7, "0123456789-/.ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz :")):
            try:
                text = self.engine.read_text(crop, psm=psm, whitelist=wl.replace(" ", "")).strip()
            except OcrError:
                continue
            for line in text.splitlines():
                line = re.sub(r"^[^\w/]+", "", line.strip())
                if line and line not in out:
                    out.append(line)
        return out

    def candidates(self, row: StatementRow, col: str) -> list[Decimal]:
        if self.doc is None or self.engine is None or col not in row.boxes:
            return []
        img = self._image(row.page)
        x0, y0, x1, y1 = row.boxes[col]
        f = REREAD_DPI / DPI
        x1 = img.width if x1 is None else x1 * f
        box = (int(x0 * f), max(0, int(y0 * f)), int(x1), min(img.height, int(y1 * f)))
        crop = img.crop(box)
        found: list[Decimal] = []
        for psm in (7, 6, 13):
            try:
                text = self.engine.read_text(crop, psm=psm, whitelist="0123456789,.CrDr-")
            except OcrError:
                continue
            for m in _AMOUNT.finditer(text.replace(" ", "")):
                try:
                    v = Decimal(m.group(1).replace(",", "") + "." + m.group(2))
                except InvalidOperation:
                    continue
                if v not in found:
                    found.append(v)
        return found


def _opening(row: StatementRow, nxt: Optional[StatementRow], rereader: Optional[_Rereader]) -> bool:
    """The first balance has no predecessor: confirm it with the next row instead.
    Returns True when the opening balance is proven by the next row."""
    if row.kind == "bf" and row.balance is not None and row.deposit == row.balance:
        return True       # B/F prints the amount twice; two identical readings confirm each other
    cands = [v for v in (row.balance, row.deposit) if v is not None]
    if rereader is not None:
        cands += rereader.candidates(row, "b") + rereader.candidates(row, "d")
    if nxt is not None and nxt.balance is not None:
        proven = [c for c in cands if _balanced(c, nxt.withdrawal, nxt.deposit, nxt.balance)]
        if proven:
            if row.balance != proven[0]:
                row.notes.append(f"Opening balance confirmed by the next row (OCR read '{row.raw.get('b', '')}').")
                row.status = "Re-read"
            row.balance = proven[0]
            if row.kind == "bf" and row.deposit is not None:
                row.deposit = row.balance
            return True
    if row.balance is None and cands:
        row.balance = cands[0]
    if row.balance is None:
        row.status = "Check"
        row.notes.append("Opening balance could not be read.")
    elif row.status == "OK":
        row.status = "Check"
        row.notes.append("Opening balance could not be confirmed by the following row.")
    return False


def _set_amount_from_delta(row: StatementRow, delta: Decimal) -> None:
    row.withdrawal, row.deposit = (-delta, None) if delta < 0 else (None, delta)


def reconcile(rows: list[StatementRow], rereader: Optional[_Rereader] = None) -> None:
    """Check every row against the running balance and repair what can be proven.

    A chain of *trust* is kept: a balance is trusted when it was read directly
    and balances with the row's own amount, or is confirmed by the next row.
    Repairs that rely on an untrusted previous balance are never shown as OK,
    because two misreads can agree with each other by accident (for example a
    pen mark read as the same extra leading digit on two neighbouring rows)."""
    # Pre-pass: a balance that could not be read is recovered from the next row
    # when that row's own amount and balance were read.
    for i in range(len(rows) - 1):
        r, n = rows[i], rows[i + 1]
        if r.balance is None and n.balance is not None and (n.withdrawal or n.deposit) and rereader is not None:
            for b in rereader.candidates(r, "b"):
                if _balanced(b, n.withdrawal, n.deposit, n.balance):
                    r.balance = b
                    r.status = "Re-read"
                    r.notes.append("Balance re-read from the scan.")
                    break
        if r.balance is None and n.balance is not None and (n.withdrawal or n.deposit):
            r.balance = n.balance + (n.withdrawal or 0) - (n.deposit or 0)
            r.status = "Inferred"
            r.notes.append("Balance (unreadable on the scan) computed from the next row.")
            # The next row's amount built this balance, so it is no longer independent proof.
            n.notes.append("Checked only against an inferred previous balance.")
            n.status = "Inferred"

    prev: Optional[Decimal] = None
    trusted = False
    for i, row in enumerate(rows):
        nxt = rows[i + 1] if i + 1 < len(rows) else None
        if row.kind == "bf" or prev is None:
            trusted = _opening(row, nxt, rereader)
            prev = row.balance
            continue
        amount = row.withdrawal or row.deposit
        next_confirms = lambda b: nxt is not None and _balanced(b, nxt.withdrawal, nxt.deposit, nxt.balance)

        # 0) read directly and balanced
        if _balanced(prev, row.withdrawal, row.deposit, row.balance):
            if not trusted and nxt is not None and not next_confirms(row.balance):
                # balances only against a doubtful previous balance: the same
                # misread on both rows would look exactly like this
                row.status = "Check"
                row.notes.append(_UNCONFIRMED[0])
                prev = row.balance
                continue
            trusted = row.status != "Inferred"
            prev = row.balance
            continue

        # 0b) balance came from the next row: derive this row's amount from it
        if trusted and row.status == "Inferred" and row.balance is not None and not amount and \
                any(n.startswith("Balance (unreadable") for n in row.notes):
            delta = row.balance - prev
            if delta != 0:
                _set_amount_from_delta(row, delta)
                row.notes.append("Amount computed from the change in balance.")
                trusted = False
                prev = row.balance
                continue

        # 1) re-synchronise: the previous balance is doubtful, but this row's own
        #    reading (amount + balance) is confirmed by the next row. Then the
        #    previous balance must be balance + withdrawal - deposit.
        if not trusted and row.balance is not None and amount and next_confirms(row.balance):
            # The balance is proven by the next row, but the amount is not: either
            # the amount or the previous balance is misread. A re-read amount that
            # balances against the previous balance AS READ proves both.
            if rereader is not None:
                fixed = next(((w, d) for w in [None] + rereader.candidates(row, "w")
                              for d in [None] + rereader.candidates(row, "d")
                              if not (w and d) and _balanced(prev, w, d, row.balance)), None)
                if fixed:
                    row.withdrawal, row.deposit = fixed
                    row.status = "Re-read"
                    row.notes.append("Amount re-read from the scan; confirmed by both neighbouring balances.")
                    trusted = True
                    prev = row.balance
                    continue
            p = rows[i - 1]
            implied_prev = row.balance + (row.withdrawal or 0) - (row.deposit or 0)
            if p.balance != implied_prev and p.kind != "bf":
                p.notes.append(f"Balance corrected to {implied_prev:,.2f} from the following rows "
                               f"(had {p.balance if p.balance is not None else 'nothing'}).")
                p.balance = implied_prev
                if p.status in ("OK", "Re-read", "Corrected"):
                    p.status = "Inferred"
            row.status = "Inferred"
            row.notes.append("Balance confirmed by the next row; the amount is as read but could not be "
                             "cross-checked because the previous balance was doubtful.")
            trusted = True
            prev = row.balance
            continue

        # 2) re-read the cells; accept only a combination that balances
        if rereader is not None:
            cw = [row.withdrawal] + rereader.candidates(row, "w") + [None]
            cd = [row.deposit] + rereader.candidates(row, "d") + [None]
            cb = [row.balance] + rereader.candidates(row, "b")
            options = [(w, d, b) for b in cb for w in cw for d in cd
                       if b is not None and _balanced(prev, w, d, b) and not (w and d)]
            # prefer a combination whose balance the next row also confirms
            options.sort(key=lambda o: not next_confirms(o[2]))
            if options:
                w, d, b = options[0]
                changed = [n for n, old, new in (("withdrawal", row.withdrawal, w), ("deposit", row.deposit, d),
                                                 ("balance", row.balance, b)) if old != new]
                row.withdrawal, row.deposit, row.balance = w, d, b
                confirmed = trusted or next_confirms(b)
                row.status = "Re-read" if confirmed else "Check"
                row.notes.append("Re-read from the scan: " + ", ".join(changed) + "."
                                 + ("" if confirmed else " Not confirmed: the previous balance is unverified."))
                trusted = confirmed
                prev = row.balance
                continue

        delta = (row.balance - prev) if row.balance is not None else None
        # 3) amount in the wrong column
        if delta is not None and amount is not None and abs(delta) == amount and not (row.withdrawal and row.deposit):
            row.withdrawal, row.deposit = (amount, None) if delta < 0 else (None, amount)
            row.status = "Corrected" if trusted else "Check"
            row.notes.append("Amount moved to the correct column (balance went " + ("down" if delta < 0 else "up") + ").")
            prev = row.balance
            continue

        # 4) balance misread: the printed amounts plus the next row prove the balance
        if amount and trusted:
            implied = prev - (row.withdrawal or 0) + (row.deposit or 0)
            if next_confirms(implied):
                row.notes.append(f"Balance computed from the amounts (OCR read '{row.raw.get('b', '')}').")
                row.balance = implied
                row.status = "Inferred"
                prev = implied
                continue

        # 5) amount missing: two trusted balances prove the amount. (If an amount
        #    WAS read and disagrees, either the amount or the balance is wrong -
        #    that is not provable, so it falls through to Check.)
        if delta is not None and delta != 0 and trusted and not amount and \
                (nxt is None or next_confirms(row.balance)):
            _set_amount_from_delta(row, delta)
            row.status = "Inferred"
            row.notes.append("Amount computed from the change in balance (OCR read "
                             f"W '{row.raw.get('w', '')}', D '{row.raw.get('d', '')}').")
            prev = row.balance
            continue

        row.status = "Check"
        row.notes.append("Does not reconcile with the running balance - compare with the PDF.")
        trusted = False
        prev = row.balance if row.balance is not None else prev

    _confirm_backwards(rows)
    check_dates(rows, rereader)


_UNCONFIRMED = ("Not confirmed: the previous balance is unverified.",
                "Opening balance could not be confirmed by the following row.")


def _confirm_backwards(rows: list[StatementRow]) -> None:
    """Promote rows held back only for lack of confirmation once the following
    row - whose own values were read, not inferred - balances against them.
    Processed from the end so confirmation can travel back to the opening row."""
    read = ("OK", "Re-read", "Corrected")
    for i in range(len(rows) - 2, -1, -1):
        row, nxt = rows[i], rows[i + 1]
        if row.status != "Check" or not any(u in n for n in row.notes for u in _UNCONFIRMED):
            continue
        if nxt.status not in read or not _balanced(row.balance, nxt.withdrawal, nxt.deposit, nxt.balance):
            continue
        if i > 0 and row.kind != "bf" and not _balanced(rows[i - 1].balance, row.withdrawal, row.deposit, row.balance):
            continue
        row.notes = [n for n in row.notes if not any(u in n for u in _UNCONFIRMED)]
        row.notes.append("Confirmed by the following row.")
        row.status = "Re-read" if any(n.startswith("Re-read") for n in row.notes) else "OK"


def check_dates(rows: list[StatementRow], rereader: Optional["_Rereader"] = None) -> None:
    """Dates must be valid and must not go backwards. A misread digit in a date
    (e.g. '34-05-2019', or '19-03' between two '17-03' rows) cannot be repaired
    by the balance check, so such rows are flagged rather than trusted."""
    dated = [(i, r.date) for i, r in enumerate(rows) if r.kind == "txn"]
    for k, (i, d) in enumerate(dated):
        row = rows[i]
        problem = ""
        if d is None:
            problem = f"Date '{row.date_text}' is missing or not a valid date."
        else:
            before = next((x for _, x in reversed(dated[:k]) if x is not None), None)
            after = next((x for _, x in dated[k + 1:] if x is not None), None)
            if (before and d < before) or (after and d > after):
                problem = f"Date '{row.date_text}' is out of order with its neighbours - possible misread."
        if problem and rereader is not None:
            before = next((x for _, x in reversed(dated[:k]) if x is not None), None)
            after = next((x for _, x in dated[k + 1:] if x is not None), None)
            for cand in rereader.text_lines(row):
                m = _DATE.match(cand) or _DATE_SPACED.match(cand)
                new = parse_statement_date(cand) if m else None
                if new and (before is None or new >= before) and (after is None or new <= after):
                    old = row.date_text
                    row.date_text = cand[:m.end()]
                    if not row.particulars:
                        row.particulars = cand[m.end():].strip()
                    row.notes.append(f"Date re-read from the scan (first reading '{old}')." if old
                                     else "Date and particulars re-read from the scan.")
                    if row.status == "OK":
                        row.status = "Re-read"
                    dated[k] = (i, new)
                    problem = ""
                    break
        if problem:
            row.notes.append(problem)
            if row.status in ("OK", "Re-read", "Corrected"):
                row.status = "Check"


def repair_with_totals(result: StatementResult) -> None:
    """Use the bank's printed totals as a second, independent proof.

    For each totals line, the withdrawals (or deposits) of the rows since the
    previous totals line must add up to the printed figure (cumulative or
    per-page). If they do not, and exactly ONE doubtful row can absorb the
    difference while still satisfying its running-balance equation, that
    value is proven by two independent sources and is corrected."""
    rows = result.rows
    cps = [c for c in result.checkpoints if 0 <= c.after_row < len(rows)]
    for k, cp in enumerate(cps):
        start = cps[k - 1].after_row + 1 if k else 0
        prev_cp = cps[k - 1] if k else None
        for col, printed, prev_printed in (
                ("withdrawal", cp.withdrawals, prev_cp.withdrawals if prev_cp else Decimal(0)),
                ("deposit", cp.deposits, prev_cp.deposits if prev_cp else Decimal(0))):
            if printed is None:
                continue
            interval = sum((getattr(r, col) or Decimal(0)) for r in rows[start:cp.after_row + 1])
            targets = [printed] + ([printed - prev_printed] if prev_printed is not None else [])
            for target in targets:          # per-page totals, or running (cumulative) totals
                diff = target - interval
                if diff == 0:
                    break
                fixes = []
                for i in range(max(start, 1), cp.after_row + 1):
                    r = rows[i]
                    other = r.deposit if col == "withdrawal" else r.withdrawal
                    if r.status == "OK" or r.kind == "bf" or other:
                        continue
                    new = (getattr(r, col) or Decimal(0)) + diff
                    if new <= 0:
                        continue
                    w, d = (new, None) if col == "withdrawal" else (None, new)
                    if _balanced(rows[i - 1].balance, w, d, r.balance):
                        fixes.append((i, new))
                if len(fixes) == 1:
                    i, new = fixes[0]
                    r = rows[i]
                    old = getattr(r, col)
                    setattr(r, col, new)
                    r.status = "Corrected"
                    r.notes.append(f"{col.capitalize()} {new:,.2f} is proven by the bank's printed totals and the "
                                   f"running balance (OCR read {old if old is not None else 'nothing'}).")
                    break


def verify_checkpoints(result: StatementResult) -> None:
    """Compare each printed total (withdrawals, deposits, balance) that could be
    read with the computed figure. Running and per-page totals both count."""
    tw = td = Decimal(0)
    cum: list[tuple[Decimal, Decimal, Optional[Decimal]]] = []
    for r in result.rows:
        tw += r.withdrawal or 0
        td += r.deposit or 0
        cum.append((tw, td, r.balance))
    prev = None
    for cp in result.checkpoints:
        if not 0 <= cp.after_row < len(cum):
            continue
        cw, cd, cb = cum[cp.after_row]
        cp.computed = (cw, cd, cb)
        checks = []
        if cp.balance is not None:
            checks.append(cb == cp.balance)
        if cp.withdrawals is not None:
            checks.append(cp.withdrawals in (cw, cw - (prev.computed[0] if prev else 0)))
        if cp.deposits is not None:
            checks.append(cp.deposits in (cd, cd - (prev.computed[1] if prev else 0)))
        cp.matches = all(checks) if checks else None
        prev = cp


# ---------------------------------------------------------------- entry point

def extract_statement(path: Path, ocr: OcrEngine, pages: list[int], lang: str = "eng",
                      password: Optional[str] = None, ocr_mode: str = "auto", timeout: int = 180,
                      progress: Optional[ProgressFn] = None,
                      is_cancelled: Callable[[], bool] = lambda: False) -> StatementResult:
    """Extract and verify a bank statement. Raises StatementError if no statement columns are found."""
    import pdfplumber
    from .extractor import Cancelled

    progress = progress or (lambda msg, done, total: None)
    result = StatementResult(source=Path(path))
    with PDFIUM_LOCK:
        doc = pdfium.PdfDocument(str(path), password=password or None)
    plumber = pdfplumber.open(str(path), password=password or "")
    status = ocr.detect() if ocr_mode != "off" else None
    used_ocr = False
    last_cols: Optional[Columns] = None
    try:
        for n, page_no in enumerate(pages, start=1):
            if is_cancelled():
                raise Cancelled()
            progress(f"Reading statement page {page_no} ({n} of {len(pages)})", n - 1, len(pages))
            ppage = plumber.pages[page_no - 1]
            text_chars = sum(1 for c in ppage.chars if c.get("text", "").strip())
            image = None
            page_ocr = False
            if text_chars >= 50 and ocr_mode != "always":
                words = _text_words(ppage)
                height = float(ppage.height) * PT
            else:
                if not status or not status.available:
                    raise StatementError("This statement is scanned and needs OCR, but the Tesseract OCR engine "
                                         "is not available (or OCR is turned off).")
                with PDFIUM_LOCK:
                    p = doc[page_no - 1]
                    try:
                        image = p.render(scale=DPI / 72).to_pil().convert("L")
                    finally:
                        p.close()
                words = _ocr_words(ocr, image, lang, timeout)
                height = image.height
                page_ocr = used_ocr = True
            ppage.close()
            sections = find_sections(words, height)
            if last_cols is not None:
                # Rows above the first header continue the previous page's table.
                first_header = sections[0].top - 120 if sections else height
                carry = Columns(last_cols.text_right, last_cols.cheque, last_cols.w_left, last_cols.wd,
                                last_cols.db, top=0, bottom=first_header)
                if first_header > 200:
                    sections.insert(0, carry)
            if not sections:
                result.warnings.append(f"Page {page_no}: no statement column headers found; page skipped.")
                continue
            if not result.header_text:
                first_top = sections[0].top
                head_lines = _group_lines([w for w in words if w.yc < first_top - 40], 18)
                result.header_text = [" ".join(w.text for w in l) for l in head_lines]
            for cols in sections:
                strips = _strip_words(ocr, image, cols, timeout) if page_ocr else None
                rows_from_section(words, cols, page_no, result.rows, result.checkpoints, strips)
            last_cols = sections[-1]
            result.pages_used.append(page_no)
        if not result.rows:
            raise StatementError("No statement rows (dates with balances) were found. "
                                 "Use the normal conversion for this document.")
        result.method = "ocr" if used_ocr else "text"
        progress("Verifying running balance (re-reading doubtful cells)", len(pages), len(pages))
        reconcile(result.rows, _Rereader(doc, ocr, lang) if used_ocr else None)
        repair_with_totals(result)
        verify_checkpoints(result)
    finally:
        plumber.close()
        with PDFIUM_LOCK:
            doc.close()
    checks = result.count("Check")
    if checks:
        result.warnings.append(f"{checks} row(s) do not reconcile with the running balance and are marked 'Check'.")
    inferred = result.count("Inferred")
    if inferred:
        result.warnings.append(f"{inferred} value(s) were computed from the running balance and are marked 'Inferred'.")
    bad_cp = [c for c in result.checkpoints if c.matches is False]
    if bad_cp:
        result.warnings.append(f"{len(bad_cp)} printed total(s) differ from the computed totals.")
    return result
