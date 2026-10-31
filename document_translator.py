# -*- coding: utf-8 -*-
"""
Document translator
===================
A secure, fully offline desktop tool to translate invoices, agreements and
other documents (PDF, image, Word, Excel/CSV) with a PyQt interface.

* Everything runs on your computer. Documents are never uploaded anywhere.
* Translation engine : Argos Translate (offline neural translation)
* Scanned pages/images: RapidOCR (offline OCR, no separate software needed)
* The original file is never modified - results are saved as a NEW file.

Run in IDLE (F5) or:  python document_translator.py
On the very first run the required libraries are installed automatically
(internet needed only for that one-time install).  When the program is
packaged as an .exe (PyInstaller) the install step is skipped.

Recommended Python: 3.10 - 3.12 (64-bit).

Language packs are handled automatically.  The first time a language pair is
needed, the app asks once to download that pack (model file only - no document
data is ever sent); after that it works fully offline.  For computers that
never go online, put the .argosmodel files in a folder named "language_packs"
next to this program and they are installed silently.
"""

import sys
import os
import atexit
import csv
import html
import importlib
import importlib.util
import math
import re
import shutil
import subprocess
import tempfile
import time
import traceback
from pathlib import Path

APP_NAME = "Document translator"

# --------------------------------------------------------------------------
# 1. One-time automatic installation of required libraries (.py script only)
# --------------------------------------------------------------------------
REQUIRED = [  # (import name, pip name)
    ("PyQt6", "PyQt6"),
    ("fitz", "PyMuPDF"),
    ("docx", "python-docx"),
    ("openpyxl", "openpyxl"),
    ("argostranslate", "argostranslate"),
    ("rapidocr_onnxruntime", "rapidocr-onnxruntime"),
    ("langdetect", "langdetect"),
]
FLAG_DIR = Path.home() / ".document_translator"
FLAG_FILE = FLAG_DIR / "deps_installed.flag"


def ensure_dependencies():
    """Install missing libraries once. Skipped completely inside an .exe."""
    if getattr(sys, "frozen", False):          # PyInstaller build
        return
    if FLAG_FILE.exists():                      # already done once
        return
    missing = [pip for mod, pip in REQUIRED if importlib.util.find_spec(mod) is None]
    if missing:
        print("First run: installing required libraries (one time only):")
        print("   " + ", ".join(missing))
        cmd = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check"] + missing
        try:
            subprocess.check_call(cmd)
        except Exception as exc:                # noqa
            print("\nAutomatic installation failed:", exc)
            print("Please run this command manually, then start the program again:")
            print("   pip install " + " ".join(missing))
            raise SystemExit(1)
        importlib.invalidate_caches()
    try:
        FLAG_DIR.mkdir(parents=True, exist_ok=True)
        FLAG_FILE.write_text("ok", encoding="utf-8")
    except OSError:
        pass


ensure_dependencies()

# --------------------------------------------------------------------------
# 2. Imports (after the install step)
# --------------------------------------------------------------------------
try:
    import fitz  # PyMuPDF
    from PyQt6.QtCore import Qt, QRect, QSize, QSizeF, QMarginsF, QThread, QTimer, pyqtSignal
    from PyQt6.QtGui import (QImage, QPixmap, QPainter, QColor, QPen, QFont,
                             QKeySequence, QShortcut, QTextDocument, QPdfWriter,
                             QPageSize, QPageLayout)
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QLabel, QPushButton, QComboBox,
        QSpinBox, QScrollArea, QSplitter, QTabWidget, QTextEdit, QFileDialog,
        QMessageBox, QInputDialog, QLineEdit, QHBoxLayout, QVBoxLayout,
        QGridLayout, QFrame, QProgressBar, QDialog, QListWidget)
except ImportError as _exc:                      # pragma: no cover
    try:
        FLAG_FILE.unlink()
    except OSError:
        pass
    print("A required library is missing:", _exc)
    print("Please restart the program (it will try to install it again).")
    raise SystemExit(1)

# --------------------------------------------------------------------------
# 3. Constants / theme  (white, blue and red)
# --------------------------------------------------------------------------
BLUE_DARK = "#0D47A1"
BLUE = "#1565C0"
BLUE_LIGHT = "#E3F2FD"
BLUE_MID = "#90CAF9"
RED = "#D32F2F"
RED_DARK = "#B71C1C"
WHITE = "#FFFFFF"

BASE_SCALE = 1.4            # zoom 100% == 1.4 x PDF points
MIN_ZOOM, MAX_ZOOM = 0.25, 4.0

PDF_EXT = {".pdf"}
IMG_NATIVE = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff"}
IMG_EXT = IMG_NATIVE | {".webp"}
WORD_EXT = {".docx"}
EXCEL_EXT = {".xlsx", ".xlsm", ".csv"}

FALLBACK_LANGS = [
    ("Arabic", "ar"), ("Catalan", "ca"), ("Chinese", "zh"), ("Czech", "cs"),
    ("Danish", "da"), ("Dutch", "nl"), ("English", "en"), ("Finnish", "fi"),
    ("French", "fr"), ("German", "de"), ("Greek", "el"), ("Hebrew", "he"),
    ("Hindi", "hi"), ("Hungarian", "hu"), ("Indonesian", "id"), ("Italian", "it"),
    ("Japanese", "ja"), ("Korean", "ko"), ("Persian", "fa"), ("Polish", "pl"),
    ("Portuguese", "pt"), ("Russian", "ru"), ("Spanish", "es"), ("Swedish", "sv"),
    ("Turkish", "tr"), ("Ukrainian", "uk"),
]
LANG_NAMES = {code: name for name, code in FALLBACK_LANGS}
LANG_NAMES.update({"mr": "Marathi", "ta": "Tamil", "te": "Telugu", "bn": "Bengali",
                   "gu": "Gujarati", "pa": "Punjabi", "ur": "Urdu", "kn": "Kannada",
                   "ml": "Malayalam", "ne": "Nepali", "th": "Thai", "vi": "Vietnamese"})
# Standard language set prepared once (each language <-> English)
BUNDLE_CODES = ["de", "fr", "hi", "pl", "zh", "ja"]

STYLESHEET = f"""
QMainWindow, QDialog {{ background: {WHITE}; }}
QWidget {{ font-family: 'Segoe UI', 'Arial'; font-size: 13px; color: #1A237E; }}
QFrame#header {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {BLUE_DARK}, stop:1 #1E88E5);
}}
QFrame#redStrip {{ background: {RED}; }}
QLabel#title {{ color: white; font-size: 26px; font-weight: 800; }}
QLabel#subtitle {{ color: {BLUE_LIGHT}; font-size: 12px; }}
QFrame#panel {{
    background: {BLUE_LIGHT}; border: 1px solid {BLUE_MID}; border-radius: 10px;
}}
QFrame#navbar {{
    background: {WHITE}; border: 1px solid {BLUE_MID}; border-radius: 10px;
}}
QLabel#cap {{ color: {BLUE_DARK}; font-weight: 700; }}
QLabel#hint {{ color: {RED_DARK}; font-weight: 600; }}
QPushButton {{
    background: {BLUE}; color: white; border: none; border-radius: 7px;
    padding: 7px 14px; font-weight: 700;
}}
QPushButton:hover {{ background: #1E88E5; }}
QPushButton:pressed {{ background: {BLUE_DARK}; }}
QPushButton:disabled {{ background: #B0BEC5; color: #ECEFF1; }}
QPushButton#red {{ background: {RED}; }}
QPushButton#red:hover {{ background: #E53935; }}
QPushButton#red:pressed {{ background: {RED_DARK}; }}
QPushButton#red:disabled {{ background: #CFB5B5; }}
QPushButton#outline {{
    background: white; color: {BLUE}; border: 2px solid {BLUE};
}}
QPushButton#outline:hover {{ background: {BLUE_LIGHT}; }}
QPushButton#outline:disabled {{ color: #B0BEC5; border-color: #B0BEC5; }}
QComboBox, QSpinBox, QLineEdit {{
    background: white; border: 2px solid {BLUE_MID}; border-radius: 6px;
    padding: 4px 8px; min-height: 22px; color: #0D2A6B;
}}
QComboBox:hover, QSpinBox:hover {{ border-color: {BLUE}; }}
QComboBox QAbstractItemView {{
    background: white; color: #0D2A6B; selection-background-color: {RED};
    selection-color: white;
}}
QScrollArea {{ background: #CFD8DC; border: 2px solid {BLUE}; border-radius: 8px; }}
QTabWidget::pane {{ border: 2px solid {BLUE}; border-radius: 8px; background: white; }}
QTabBar::tab {{
    background: {BLUE_LIGHT}; color: {BLUE_DARK}; padding: 8px 18px;
    border-top-left-radius: 8px; border-top-right-radius: 8px; font-weight: 700;
}}
QTabBar::tab:selected {{ background: {BLUE}; color: white; }}
QTextEdit {{ background: white; color: #111; border: none; font-size: 14px; }}
QProgressBar {{
    border: 1px solid {BLUE}; border-radius: 6px; text-align: center; height: 16px;
    background: white; color: {BLUE_DARK};
}}
QProgressBar::chunk {{ background: {RED}; border-radius: 5px; }}
QStatusBar {{ background: {BLUE_LIGHT}; color: {BLUE_DARK}; }}
QListWidget {{ border: 2px solid {BLUE_MID}; border-radius: 6px; }}
QListWidget::item:selected {{ background: {RED}; color: white; }}
QSplitter::handle {{ background: {BLUE_MID}; width: 4px; }}
"""


# --------------------------------------------------------------------------
# 4. Helpers: file conversion (Word / Excel -> PDF for page view)
# --------------------------------------------------------------------------
def _print_document(doc, writer):
    printer = getattr(doc, "print_", None) or getattr(doc, "print")
    printer(writer)


def html_to_pdf(html_text, dst):
    """Render HTML to a paged PDF using Qt only (no extra software)."""
    doc = QTextDocument()
    doc.setDefaultFont(QFont("Arial", 10))
    doc.setHtml(html_text)
    writer = QPdfWriter(dst)
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageMargins(QMarginsF(15, 15, 15, 15), QPageLayout.Unit.Millimeter)
    _print_document(doc, writer)


def text_to_pdf(text, dst):
    doc = QTextDocument()
    doc.setDefaultFont(QFont("Arial", 11))
    doc.setPlainText(text)
    writer = QPdfWriter(dst)
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageMargins(QMarginsF(15, 15, 15, 15), QPageLayout.Unit.Millimeter)
    _print_document(doc, writer)


def docx_to_pdf(src, dst):
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    d = docx.Document(src)
    parts = ["<html><body>"]
    for child in d.element.body.iterchildren():
        tag = child.tag.split("}")[-1]
        if tag == "p":
            p = Paragraph(child, d)
            esc = html.escape(p.text) or "&nbsp;"
            style = p.style.name if p.style is not None and p.style.name else ""
            if style.startswith("Heading") or style == "Title":
                parts.append(f"<h2>{esc}</h2>")
            else:
                parts.append(f"<p>{esc}</p>")
        elif tag == "tbl":
            t = Table(child, d)
            parts.append("<table border='1' cellspacing='0' cellpadding='4' width='100%'>")
            for row in t.rows:
                parts.append("<tr>")
                seen = set()
                for cell in row.cells:
                    if id(cell._tc) in seen:
                        continue
                    seen.add(id(cell._tc))
                    parts.append(f"<td>{html.escape(cell.text) or '&nbsp;'}</td>")
                parts.append("</tr>")
            parts.append("</table><p>&nbsp;</p>")
    parts.append("</body></html>")
    html_to_pdf("".join(parts), dst)


def _table_html(title, rows):
    out = [f"<h2>{html.escape(title)}</h2>",
           "<table border='1' cellspacing='0' cellpadding='3' width='100%'>"]
    for r in rows:
        out.append("<tr>" + "".join(f"<td>{html.escape(c) or '&nbsp;'}</td>" for c in r) + "</tr>")
    out.append("</table><p>&nbsp;</p>")
    return "".join(out)


MAX_SHEET_ROWS = 5000


def excel_to_pdf(src, dst):
    ext = Path(src).suffix.lower()
    parts = ["<html><body>"]
    if ext == ".csv":
        with open(src, newline="", encoding="utf-8-sig", errors="replace") as fh:
            rows = []
            for i, r in enumerate(csv.reader(fh)):
                if i >= MAX_SHEET_ROWS:
                    rows.append([f"... only the first {MAX_SHEET_ROWS} rows are shown ..."])
                    break
                rows.append(r)
        parts.append(_table_html(Path(src).name, rows))
    else:
        import openpyxl
        wb = openpyxl.load_workbook(src, read_only=True, data_only=True)
        try:
            for ws in wb.worksheets:
                rows = []
                for r in ws.iter_rows(values_only=True):
                    cells = ["" if v is None else str(v) for v in r]
                    if not any(c.strip() for c in cells):
                        continue
                    if len(rows) >= MAX_SHEET_ROWS:
                        rows.append([f"... only the first {MAX_SHEET_ROWS} rows are shown ..."])
                        break
                    rows.append(cells)
                if rows:
                    width = max(len(r) for r in rows)
                    rows = [r + [""] * (width - len(r)) for r in rows]
                    parts.append(_table_html(ws.title, rows))
        finally:
            wb.close()
    parts.append("</body></html>")
    html_to_pdf("".join(parts), dst)


# --------------------------------------------------------------------------
# 5. Text extraction (text layer first, offline OCR for scans/images)
# --------------------------------------------------------------------------
_OCR = None


def get_ocr():
    global _OCR
    if _OCR is None:
        from rapidocr_onnxruntime import RapidOCR
        _OCR = RapidOCR()
    return _OCR


def _item(text, rect, size, color=0, bg=None, ocr=False):
    return {"text": text, "rect": tuple(rect), "size": float(size),
            "color": int(color), "bg": bg, "ocr": ocr}


def ocr_region(page, clip):
    import numpy as np
    S = 2.5
    pix = page.get_pixmap(matrix=fitz.Matrix(S, S), clip=clip, alpha=False)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n == 1:
        arr = np.repeat(arr, 3, axis=2)
    arr = np.ascontiguousarray(arr[:, :, :3])
    result, _ = get_ocr()(arr)
    if not result:
        return []
    found = []
    for box, txt, _score in result:
        txt = (txt or "").strip()
        if not txt:
            continue
        xs = [q[0] for q in box]
        ys = [q[1] for q in box]
        found.append((min(xs), min(ys), max(xs), max(ys), txt))
    found.sort(key=lambda t: t[1])
    rows = []
    for it in found:
        h = it[3] - it[1]
        cy = (it[1] + it[3]) / 2
        if rows and abs(cy - rows[-1]["cy"]) < 0.5 * max(h, rows[-1]["h"]):
            rows[-1]["items"].append(it)
            rows[-1]["bottom"] = max(rows[-1]["bottom"], it[3])
        else:
            rows.append({"cy": cy, "h": h, "items": [it], "top": it[1], "bottom": it[3]})
    for r in rows:
        r["items"].sort(key=lambda t: t[0])

    def make(x0, y0, x1, y1, text, line_h):
        region = arr[max(int(y0), 0):int(y1) + 1, max(int(x0), 0):int(x1) + 1]
        bg = (1.0, 1.0, 1.0)
        if region.size:
            med = np.median(region.reshape(-1, 3), axis=0)
            bg = tuple(float(v) / 255 for v in med)
        lum = 0.299 * bg[0] + 0.587 * bg[1] + 0.114 * bg[2]
        color = 0 if lum > 0.5 else 0xFFFFFF
        rect = fitz.Rect(clip.x0 + x0 / S, clip.y0 + y0 / S, clip.x0 + x1 / S, clip.y0 + y1 / S)
        return _item(text, rect, max(5.0, line_h / S * 0.72), color, bg, True)

    # Table-like rows (several pieces of text) stay separate; consecutive single
    # long rows are joined into one paragraph.
    out, group = [], []

    def flush():
        if not group:
            return
        its = [r["items"][0] for r in group]
        out.append(make(min(i[0] for i in its), min(i[1] for i in its),
                        max(i[2] for i in its), max(i[3] for i in its),
                        " ".join(i[4] for i in its), group[0]["h"]))
        del group[:]

    for r in rows:
        flow = len(r["items"]) == 1 and len(r["items"][0][4]) >= 35
        if not flow:
            flush()
            for it in r["items"]:
                out.append(make(it[0], it[1], it[2], it[3], it[4], r["h"]))
        else:
            if group and (r["top"] - group[-1]["bottom"]) > 0.9 * r["h"]:
                flush()
            group.append(r)
    flush()
    return out


def _same_spot(a, b):
    """True when two boxes sit on (almost) the same spot - copies of one text."""
    iw = min(a.x1, b.x1) - max(a.x0, b.x0)
    ih = min(a.y1, b.y1) - max(a.y0, b.y0)
    if iw > 0 and ih > 0 and iw * ih >= 0.4 * min(a.get_area(), b.get_area()):
        return True
    h = min(a.height, b.height)
    w = max(a.width, b.width)
    dx = abs((a.x0 + a.x1) - (b.x0 + b.x1)) / 2
    dy = abs((a.y0 + a.y1) - (b.y0 + b.y1)) / 2
    return dx <= max(2.0, 0.15 * w) and dy <= max(1.5, 0.35 * h)


def dedupe_items(items):
    """Many PDFs print the same text 2-3 times on top of each other (fake bold,
    hidden layers).  Keep one copy; the box grows to cover all copies."""
    kept = []
    for it in items:
        r = fitz.Rect(it["rect"])
        key = " ".join(it["text"].split()).casefold()
        for k in kept:
            if k[0] == key and _same_spot(r, k[1]):
                k[1].include_rect(r)
                break
        else:
            kept.append([key, r, it])
    out = []
    for _key, r, it in kept:
        it["rect"] = tuple(r)
        out.append(it)
    return out


def extract_paragraphs(page, rect):
    """Return a list of items: text + position/size/colour on the page."""
    clip = rect if rect is not None else page.rect
    data = page.get_text("dict", clip=clip, sort=True)
    items = []
    for b in data["blocks"]:
        if b.get("type") != 0:
            continue
        lines = []
        for ln in b["lines"]:
            spans = [sp for sp in ln["spans"] if sp["text"].strip()]
            if not spans:
                continue
            lines.append({"text": "".join(sp["text"] for sp in ln["spans"]).strip(),
                          "bbox": ln["bbox"], "size": max(sp["size"] for sp in spans),
                          "color": spans[0]["color"]})
        if not lines:
            continue
        avg = sum(len(l["text"]) for l in lines) / len(lines)
        if len(lines) < 2 or avg < 45:           # table cells / short lines: keep separate
            for l in lines:
                items.append(_item(l["text"], l["bbox"], l["size"], l["color"]))
        else:                                    # flowing text: keep sentences together
            bb = (min(l["bbox"][0] for l in lines), min(l["bbox"][1] for l in lines),
                  max(l["bbox"][2] for l in lines), max(l["bbox"][3] for l in lines))
            items.append(_item(" ".join(l["text"] for l in lines), bb,
                               lines[0]["size"], lines[0]["color"]))
    if sum(len(i["text"]) for i in items) < 3:   # no text layer -> scanned / image
        items = ocr_region(page, clip)
    return dedupe_items(items)


WATERMARK_TEXT = "ONLY FOR REFERENCE"


def _sample_bg(page, rect, grow=3.5):
    """Background colour around a text box (median of the pixels just outside it)."""
    import numpy as np
    r = fitz.Rect(rect.x0 - grow, rect.y0 - grow, rect.x1 + grow, rect.y1 + grow)
    r.intersect(page.rect)
    if r.width < 1 or r.height < 1:
        return (1.0, 1.0, 1.0)
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=r, alpha=False)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n == 1:
        arr = np.repeat(arr, 3, axis=2)
    arr = arr[:, :, :3]
    k = 2
    ring = np.concatenate([arr[:k].reshape(-1, 3), arr[-k:].reshape(-1, 3),
                           arr[:, :k].reshape(-1, 3), arr[:, -k:].reshape(-1, 3)])
    med = np.median(ring, axis=0) / 255.0
    return (float(med[0]), float(med[1]), float(med[2]))


def _add_watermark(page):
    """Large diagonal, semi-transparent watermark across the page."""
    r = page.rect
    cx, cy = (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2
    angle = min(40.0, math.degrees(math.atan2(r.height, r.width)))
    diag = math.hypot(r.width, r.height)
    target = min(0.72 * diag, 0.88 * r.width / max(math.cos(math.radians(angle)), 0.3))
    fs = 40.0
    length = fitz.get_text_length(WATERMARK_TEXT, fontname="helv", fontsize=fs)
    fs = fs * target / max(length, 1.0)
    length = fitz.get_text_length(WATERMARK_TEXT, fontname="helv", fontsize=fs)
    pt = fitz.Point(cx - length / 2, cy + fs * 0.35)
    morph = (fitz.Point(cx, cy), fitz.Matrix(angle))
    try:
        page.insert_text(pt, WATERMARK_TEXT, fontsize=fs, fontname="helv",
                         color=(0.83, 0.18, 0.18), fill_opacity=0.25, morph=morph, overlay=True)
    except TypeError:                            # older PyMuPDF: no opacity support
        page.insert_text(pt, WATERMARK_TEXT, fontsize=fs, fontname="helv",
                         color=(0.95, 0.80, 0.80), morph=morph, overlay=True)


def build_layout_pdf(src_path, password, results, dst, watermark=False):
    """Copy the document and replace the original text by the translation, in place."""
    doc = fitz.open(src_path)
    if doc.needs_pass:
        doc.authenticate(password or "")
    if not doc.is_pdf:                           # images -> one-page-per-image PDF
        doc = fitz.open("pdf", doc.convert_to_pdf())
    for res in results:
        page = doc[res["page"] - 1]
        kept = []                                # (rect, translated text, item)
        for it, new in zip(res["items"], res["translated"]):
            if not new or new.strip() == it["text"].strip():
                continue
            rect = fitz.Rect(it["rect"])
            if rect.width < 1 or rect.height < 1:
                continue
            dup = any(n2.strip() == new.strip() and _same_spot(rect, r2)
                      for r2, n2, _ in kept)     # same text drawn twice (e.g. fake bold)
            if not dup:
                kept.append((rect, new, it))
        if not kept:
            continue
        bgs = [_sample_bg(page, rect) for rect, _, _ in kept]     # before anything changes

        # 1. remove the original text objects
        redacted = False
        for rect, _, it in kept:
            if not it["ocr"]:
                page.add_redact_annot(fitz.Rect(rect.x0 + 0.5, rect.y0 + 0.5,
                                                rect.x1 - 0.5, rect.y1 - 0.5), fill=False)
                redacted = True
        if redacted:
            try:
                page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE,
                                      graphics=fitz.PDF_REDACT_LINE_ART_NONE)
            except (TypeError, AttributeError):
                page.apply_redactions()

        # 2. paint the background over every box, so nothing of the old text can show through
        for (rect, _, _), bg in zip(kept, bgs):
            py = min(max(0.6, 0.18 * rect.height), 2.2)
            px = min(max(1.0, 0.18 * rect.height), 2.5)
            page.draw_rect(fitz.Rect(rect.x0 - px, rect.y0 - py, rect.x1 + px, rect.y1 + py),
                           color=None, fill=bg, overlay=True)

        # 3. write the translation (after all backgrounds, so neighbours never cover it)
        for (rect, new, it), bg in zip(kept, bgs):
            c = it["color"]
            tc = ((c >> 16) & 255, (c >> 8) & 255, c & 255)
            blum = 0.299 * bg[0] + 0.587 * bg[1] + 0.114 * bg[2]
            tlum = (0.299 * tc[0] + 0.587 * tc[1] + 0.114 * tc[2]) / 255.0
            if abs(blum - tlum) < 0.35:          # keep the text readable on any background
                tc = (0, 0, 0) if blum > 0.5 else (255, 255, 255)
            box = (f'<div style="font-size:{it["size"]:.1f}pt;color:rgb({tc[0]},{tc[1]},{tc[2]});">'
                   f'{html.escape(new)}</div>')
            try:
                page.insert_htmlbox(rect, box, scale_low=0.3,
                                    css="* {margin:0; padding:0; line-height:1.15;}")
            except Exception:                    # noqa - plain fallback
                page.insert_textbox(rect, new, fontsize=max(5.0, it["size"] * 0.8),
                                    color=tuple(v / 255 for v in tc))
    if watermark:
        for pg in doc:
            try:
                _add_watermark(pg)
            except Exception:                    # noqa
                traceback.print_exc()
    doc.save(dst, garbage=3, deflate=True)
    doc.close()


HAS_LETTER = re.compile(r"[^\W\d_]", re.UNICODE)

# --------------------------------------------------------------------------
# 6. Background workers
# --------------------------------------------------------------------------
try:
    _APP_DIR = Path(sys.executable).parent if getattr(sys, "frozen", False) \
        else Path(__file__).resolve().parent
except NameError:
    _APP_DIR = Path.cwd()
LOCAL_PACK_DIR = _APP_DIR / "language_packs"
IMPORTED_FILE = FLAG_DIR / "imported_packs.txt"


def import_local_packs():
    """Silently install any .argosmodel files found in the 'language_packs' folder."""
    try:
        files = sorted(LOCAL_PACK_DIR.glob("*.argosmodel"))
    except OSError:
        return 0
    if not files:
        return 0
    try:
        done = set(IMPORTED_FILE.read_text(encoding="utf-8").splitlines())
    except OSError:
        done = set()
    import argostranslate.package as pk
    count = 0
    for f in files:
        key = f"{f.name}|{f.stat().st_size}"
        if key in done:
            continue
        try:
            pk.install_from_path(f)
            done.add(key)
            count += 1
        except Exception:                        # noqa
            traceback.print_exc()
    if count:
        try:
            FLAG_DIR.mkdir(parents=True, exist_ok=True)
            IMPORTED_FILE.write_text("\n".join(sorted(done)), encoding="utf-8")
        except OSError:
            pass
    return count


def prepare_packs(log=print):
    """Download the standard language set ONCE, keep the files in the 'language_packs'
    folder (so they can be copied to other computers) and install them.
    Only model files are downloaded - no document data is ever sent."""
    import argostranslate.package as pk
    LOCAL_PACK_DIR.mkdir(parents=True, exist_ok=True)
    log("Contacting the language-pack index ...")
    pk.update_package_index()
    avail = pk.get_available_packages()
    want = [(c, "en") for c in BUNDLE_CODES] + [("en", c) for c in BUNDLE_CODES]
    missing = []
    for a, b in want:
        match = [x for x in avail if x.from_code == a and x.to_code == b]
        if not match:
            missing.append(f"{LANG_NAMES.get(a, a)} -> {LANG_NAMES.get(b, b)}")
            continue
        dst = LOCAL_PACK_DIR / f"{a}_{b}.argosmodel"
        if not dst.exists():
            log(f"Downloading {LANG_NAMES.get(a, a)} -> {LANG_NAMES.get(b, b)} ...")
            shutil.copyfile(match[0].download(), dst)
    log("Installing ...")
    import_local_packs()
    return missing


def pair_ready(a, b):
    import argostranslate.translate as at
    langs = {l.code: l for l in at.get_installed_languages()}
    return a in langs and b in langs and langs[a].get_translation(langs[b]) is not None


class Task(QThread):
    """Run any function in the background."""
    done = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self):
        try:
            self.done.emit(self.fn())
        except Exception as exc:                 # noqa
            self.failed.emit(str(exc) or exc.__class__.__name__)


class TranslateWorker(QThread):
    progress = pyqtSignal(int, int, str)
    finished_ok = pyqtSignal(list, dict)
    failed = pyqtSignal(str)
    ask_download = pyqtSignal(str)

    def __init__(self, path, password, jobs, src_code, tgt_code):
        super().__init__()
        self.path, self.password, self.jobs = path, password, jobs
        self.src_code, self.tgt_code = src_code, tgt_code
        self._cancel = False
        self._answer = None

    def cancel(self):
        self._cancel = True

    def answer(self, yes):
        self._answer = bool(yes)

    def _ask(self, names):
        self._answer = None
        self.ask_download.emit(names)
        while self._answer is None and not self._cancel:
            time.sleep(0.1)
        return bool(self._answer)

    def _ensure_packs(self, src, tgt):
        """Make sure src->tgt can be translated; install / download packs if needed."""
        if pair_ready(src, tgt):
            return True
        import_local_packs()
        if pair_ready(src, tgt):
            return True
        legs = []
        if src != "en":
            legs.append((src, "en"))
        if tgt != "en":
            legs.append(("en", tgt))
        legs = [lg for lg in legs if not pair_ready(*lg)]
        names = ", ".join(f"{LANG_NAMES.get(a, a)} -> {LANG_NAMES.get(b, b)}" for a, b in legs)
        offline = (f"This translation needs the language pack(s): {names}.\n\n"
                   "They are not installed and could not be downloaded (no internet?).\n"
                   "Connect to the internet once and try again, or copy the .argosmodel "
                   f"file(s) into this folder and try again:\n{LOCAL_PACK_DIR}")
        self.progress.emit(0, 0, "Checking language packs ...")
        import argostranslate.package as pk
        try:
            pk.update_package_index()
            avail = pk.get_available_packages()
        except Exception:                        # noqa
            self.failed.emit(offline)
            return False
        todo = []
        for a, b in legs:
            match = [x for x in avail if x.from_code == a and x.to_code == b]
            if not match:
                self.failed.emit(f"Translation {LANG_NAMES.get(a, a)} -> {LANG_NAMES.get(b, b)} "
                                 "is not supported by the offline engine.")
                return False
            todo.append(match[0])
        if not self._ask(", ".join(f"{x.from_name} -> {x.to_name}" for x in todo)):
            self.failed.emit("Translation cancelled.")
            return False
        try:
            for i, x in enumerate(todo):
                self.progress.emit(i, len(todo),
                                   f"Downloading language pack {x.from_name} -> {x.to_name} (one time) ...")
                pk.install_from_path(x.download())
        except Exception:                        # noqa
            self.failed.emit(offline)
            return False
        if not pair_ready(src, tgt):
            self.failed.emit("The language pack was installed but is not usable. Please try again.")
            return False
        return True

    def run(self):
        try:
            self._run()
        except Exception as exc:                 # noqa
            traceback.print_exc()
            self.failed.emit(str(exc) or exc.__class__.__name__)

    def _run(self):
        doc = fitz.open(self.path)
        if doc.needs_pass:
            doc.authenticate(self.password or "")
        extracted = []
        n = len(self.jobs)
        for i, (pno, rect) in enumerate(self.jobs):
            if self._cancel:
                self.failed.emit("Translation cancelled.")
                return
            self.progress.emit(i, n, f"Reading page {pno + 1} ...")
            extracted.append((pno, extract_paragraphs(doc[pno], rect)))
        doc.close()

        all_paras = [it["text"] for _, its in extracted for it in its]
        if not any(HAS_LETTER.search(p) for p in all_paras):
            self.failed.emit("No readable text was found in the selected content.")
            return

        import argostranslate.translate as at
        src = self.src_code
        if src == "auto":
            from langdetect import detect, DetectorFactory
            DetectorFactory.seed = 0
            sample = " ".join(all_paras)[:4000]
            try:
                src = detect(sample)
            except Exception:                    # noqa
                self.failed.emit("Could not detect the document language. "
                                 "Please choose the source language manually.")
                return
            src = {"zh-cn": "zh", "zh-tw": "zt"}.get(src, src)
        translation = None
        if src != self.tgt_code:
            if not self._ensure_packs(src, self.tgt_code):
                return
        by_code = {l.code: l for l in at.get_installed_languages()}
        src_lang, tgt_lang = by_code.get(src), by_code.get(self.tgt_code)
        if src != self.tgt_code:
            translation = src_lang.get_translation(tgt_lang) if src_lang and tgt_lang else None
            if translation is None:
                self.failed.emit("No translation path between these languages is installed.")
                return
        src_name = src_lang.name if src_lang else LANG_NAMES.get(src, src)
        tgt_name = tgt_lang.name if tgt_lang else LANG_NAMES.get(self.tgt_code, self.tgt_code)

        total = len(all_paras)
        done = 0
        cache = {}
        results = []
        for pno, its in extracted:
            out = []
            for it in its:
                p = it["text"]
                if self._cancel:
                    self.failed.emit("Translation cancelled.")
                    return
                if translation is None or not HAS_LETTER.search(p):
                    out.append(p)
                else:
                    if p not in cache:
                        cache[p] = translation.translate(p)
                    out.append(cache[p])
                done += 1
                if done % 3 == 0 or done == total:
                    self.progress.emit(done, total, f"Translating ... {done}/{total}")
            results.append({"page": pno + 1, "original": [it["text"] for it in its],
                            "translated": out, "items": its})
        self.finished_ok.emit(results, {"src_name": src_name, "tgt_name": tgt_name,
                                        "tgt_code": self.tgt_code})


# --------------------------------------------------------------------------
# 7. Page view widget with area selection
# --------------------------------------------------------------------------
class PageView(QLabel):
    selectionMade = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.sel = None
        self._origin = None

    def clear_selection(self):
        self.sel = None
        self._origin = None
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._origin = e.position().toPoint()
            self.sel = None
            self.update()

    def mouseMoveEvent(self, e):
        if self._origin is not None:
            r = QRect(self._origin, e.position().toPoint()).normalized()
            self.sel = r.intersected(self.rect())
            self.update()

    def mouseReleaseEvent(self, e):
        if self._origin is not None:
            self._origin = None
            if self.sel is None or self.sel.width() < 8 or self.sel.height() < 8:
                self.sel = None
            self.update()
            self.selectionMade.emit()

    def paintEvent(self, e):
        super().paintEvent(e)
        if self.sel is not None and not self.sel.isNull():
            p = QPainter(self)
            p.fillRect(self.sel, QColor(21, 101, 192, 55))
            pen = QPen(QColor(RED), 2, Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawRect(self.sel)
            p.end()


# --------------------------------------------------------------------------
# 9. Main window
# --------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1450, 880)
        self.tmpdir = tempfile.mkdtemp(prefix="doctrans_")
        atexit.register(shutil.rmtree, self.tmpdir, True)
        self.doc = None
        self.doc_path = None      # file fitz opens (original or temp PDF)
        self.src_path = None      # the user's original file (never modified)
        self.password = None
        self.page = 0
        self.zoom = 1.0
        self.worker = None
        self.tasks = []
        self.results = []
        self.meta = {}
        self.last_dir = str(Path.home())
        self.installed_langs = []
        self.tdoc = None
        self._preview_n = 0
        self._build_ui()
        self.refresh_languages()
        QShortcut(QKeySequence("Ctrl+O"), self, self.open_document)
        QShortcut(QKeySequence("PgDown"), self, self.next_page)
        QShortcut(QKeySequence("PgUp"), self, self.prev_page)
        QShortcut(QKeySequence("Ctrl+="), self, self.zoom_in)
        QShortcut(QKeySequence("Ctrl++"), self, self.zoom_in)
        QShortcut(QKeySequence("Ctrl+-"), self, self.zoom_out)

    # ---- UI -------------------------------------------------------------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setObjectName("header")
        hl = QVBoxLayout(header)
        hl.setContentsMargins(24, 12, 24, 12)
        t = QLabel(APP_NAME)
        t.setObjectName("title")
        s = QLabel("Secure invoice & agreement translator  |  100% offline  |  your files never leave this computer")
        s.setObjectName("subtitle")
        hl.addWidget(t)
        hl.addWidget(s)
        root.addWidget(header)
        strip = QFrame()
        strip.setObjectName("redStrip")
        strip.setFixedHeight(5)
        root.addWidget(strip)

        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(12, 10, 12, 6)
        bl.setSpacing(8)
        root.addWidget(body, 1)

        # control panel
        panel = QFrame()
        panel.setObjectName("panel")
        g = QGridLayout(panel)
        g.setContentsMargins(12, 10, 12, 10)
        g.setHorizontalSpacing(10)
        g.setVerticalSpacing(6)

        def cap(text):
            l = QLabel(text)
            l.setObjectName("cap")
            return l

        self.btn_open = QPushButton("Open document ...")
        self.btn_open.clicked.connect(self.open_document)

        self.src_combo = QComboBox()
        self.tgt_combo = QComboBox()

        self.btn_translate = QPushButton("Translate")
        self.btn_translate.setObjectName("red")
        self.btn_translate.clicked.connect(self.start_translate)
        self.btn_translate.setEnabled(False)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("outline")
        self.btn_cancel.clicked.connect(self.cancel_translate)
        self.btn_cancel.setVisible(False)
        self.btn_save = QPushButton("Save translation as ...")
        self.btn_save.clicked.connect(self.save_translation)
        self.btn_save.setEnabled(False)

        g.addWidget(cap("1. Document"), 0, 0)
        g.addWidget(cap("From language"), 0, 1)
        g.addWidget(cap("2. Translate to"), 0, 2)
        g.addWidget(self.btn_open, 1, 0)
        g.addWidget(self.src_combo, 1, 1)
        g.addWidget(self.tgt_combo, 1, 2)
        g.addWidget(self.btn_translate, 1, 3)
        g.addWidget(self.btn_cancel, 1, 4)
        g.addWidget(self.btn_save, 1, 5)
        g.setColumnStretch(6, 1)
        bl.addWidget(panel)

        # viewer + result
        split = QSplitter(Qt.Orientation.Horizontal)
        self.scroll = QScrollArea()
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.view = PageView()
        self.view.setText("Open a document to begin\n\n(Ctrl+O)")
        self.view.setStyleSheet("color:#455A64; font-size:16px;")
        self.view.setMinimumSize(400, 300)
        self.view.selectionMade.connect(self.on_selection)
        self.scroll.setWidget(self.view)
        self.scroll.setWidgetResizable(True)
        split.addWidget(self.scroll)

        self.tabs = QTabWidget()
        self.out_text = QTextEdit()
        self.out_text.setReadOnly(True)
        self.out_text.setPlaceholderText("The translation will appear here.")
        self.orig_text = QTextEdit()
        self.orig_text.setReadOnly(True)
        self.orig_text.setPlaceholderText("The extracted original text will appear here.")
        self.tview = QLabel("The translated document will appear here,\n"
                            "in the same layout as the original.")
        self.tview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tview.setStyleSheet("color:#455A64; font-size:15px;")
        self.tscroll = QScrollArea()
        self.tscroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tscroll.setWidget(self.tview)
        self.tscroll.setWidgetResizable(True)
        self.tabs.addTab(self.tscroll, "Translated document")
        self.tabs.addTab(self.out_text, "Translation text")
        self.tabs.addTab(self.orig_text, "Original text")
        for a_bar, b_bar in ((self.scroll.verticalScrollBar(), self.tscroll.verticalScrollBar()),
                             (self.scroll.horizontalScrollBar(), self.tscroll.horizontalScrollBar())):
            a_bar.valueChanged.connect(b_bar.setValue)     # both panes scroll together
            b_bar.valueChanged.connect(a_bar.setValue)
        split.addWidget(self.tabs)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        bl.addWidget(split, 1)

        # navigation bar
        nav = QFrame()
        nav.setObjectName("navbar")
        nl = QHBoxLayout(nav)
        nl.setContentsMargins(10, 6, 10, 6)
        self.btn_prev = QPushButton("< Previous")
        self.btn_prev.clicked.connect(self.prev_page)
        self.btn_next = QPushButton("Next >")
        self.btn_next.clicked.connect(self.next_page)
        self.spin = QSpinBox()
        self.spin.setRange(1, 1)
        self.spin.setSuffix("/1")
        self.spin.setKeyboardTracking(False)
        self.spin.setMinimumWidth(95)
        self.spin.setToolTip("Type a page number and press Enter to jump")
        self.spin.valueChanged.connect(lambda v: self.go_to(v - 1))
        self.btn_zout = QPushButton("Zoom -")
        self.btn_zout.setObjectName("outline")
        self.btn_zout.clicked.connect(self.zoom_out)
        self.zoom_lbl = QLabel("100%")
        self.zoom_lbl.setObjectName("cap")
        self.zoom_lbl.setMinimumWidth(48)
        self.zoom_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.btn_zin = QPushButton("Zoom +")
        self.btn_zin.setObjectName("outline")
        self.btn_zin.clicked.connect(self.zoom_in)
        self.btn_fit = QPushButton("Fit width")
        self.btn_fit.setObjectName("outline")
        self.btn_fit.clicked.connect(self.fit_width)
        self.btn_clear = QPushButton("Clear selection")
        self.btn_clear.setObjectName("red")
        self.btn_clear.clicked.connect(self.clear_selection)
        self.sel_lbl = QLabel("No document open")
        self.sel_lbl.setObjectName("hint")
        for w in (self.btn_prev, self.spin, self.btn_next):
            nl.addWidget(w)
        nl.addSpacing(18)
        for w in (self.btn_zout, self.zoom_lbl, self.btn_zin, self.btn_fit):
            nl.addWidget(w)
        nl.addSpacing(18)
        nl.addWidget(self.btn_clear)
        nl.addStretch(1)
        nl.addWidget(self.sel_lbl)
        bl.addWidget(nav)
        self._nav_widgets = [self.btn_prev, self.btn_next, self.spin, self.btn_zout,
                             self.btn_zin, self.btn_fit, self.btn_clear]
        self._set_nav_enabled(False)

        # status bar
        self.progress = QProgressBar()
        self.progress.setFixedWidth(260)
        self.progress.setVisible(False)
        self.statusBar().addWidget(self.progress)
        lock = QLabel("OFFLINE MODE - no data is uploaded or shared")
        lock.setObjectName("hint")
        self.statusBar().addPermanentWidget(lock)
        self.statusBar().showMessage("Ready")

    def _set_nav_enabled(self, on):
        for w in self._nav_widgets:
            w.setEnabled(on)

    def info(self, msg):
        self.statusBar().showMessage(msg, 8000)

    def error(self, msg, title="Problem"):
        QMessageBox.critical(self, f"{APP_NAME} - {title}", msg)

    # ---- background helper ---------------------------------------------
    def run_task(self, fn, ok, fail):
        task = Task(fn)
        task.done.connect(ok)
        task.failed.connect(fail)

        def cleanup():
            if task in self.tasks:
                self.tasks.remove(task)
        task.finished.connect(cleanup)
        self.tasks.append(task)
        task.start()

    # ---- languages ------------------------------------------------------
    def refresh_languages(self):
        def fn():
            try:
                import_local_packs()
            except Exception:                    # noqa
                traceback.print_exc()
            import argostranslate.translate as at
            return sorted((l.name, l.code) for l in at.get_installed_languages())
        self.run_task(fn, self._langs_loaded, self._langs_failed)

    def _fill_combo(self, combo, langs, auto, default_code):
        prev = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        if auto:
            combo.addItem("Auto-detect", "auto")
        for name, code in langs:
            combo.addItem(name, code)
        want = prev if prev is not None else default_code
        idx = combo.findData(want)
        if idx < 0:
            idx = combo.findData(default_code)
        combo.setCurrentIndex(max(idx, 0))
        combo.blockSignals(False)

    def _langs_loaded(self, langs):
        self.installed_langs = langs
        merged = {code: name for name, code in FALLBACK_LANGS}
        for name, code in langs:
            merged[code] = name
        shown = sorted(((n, c) for c, n in merged.items()), key=lambda t: t[0])
        self._fill_combo(self.src_combo, shown, True, "auto")
        self._fill_combo(self.tgt_combo, shown, False, "en")
        self.info("Ready. Language packs are fetched automatically the first time they are needed.")

    def _langs_failed(self, msg):
        self._fill_combo(self.src_combo, FALLBACK_LANGS, True, "auto")
        self._fill_combo(self.tgt_combo, FALLBACK_LANGS, False, "en")
        self.info("Could not load the translation engine: " + msg)

    # ---- opening --------------------------------------------------------
    def open_document(self):
        if self.worker is not None:
            return
        def pat(exts):
            return " ".join("*" + e for e in sorted(exts))
        flt = (f"All supported files ({pat(PDF_EXT | IMG_EXT | WORD_EXT | EXCEL_EXT)});;"
               f"PDF ({pat(PDF_EXT)});;Images ({pat(IMG_EXT)});;"
               f"Word ({pat(WORD_EXT)});;Excel / CSV ({pat(EXCEL_EXT)});;All files (*)")
        path, _ = QFileDialog.getOpenFileName(self, "Open document", self.last_dir, flt)
        if path:
            self.load_document(path)

    def load_document(self, path):
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            ext = Path(path).suffix.lower()
            base = Path(path).stem
            if ext in PDF_EXT or ext in IMG_NATIVE:
                dp = path
            elif ext == ".webp":
                dp = os.path.join(self.tmpdir, base + "_view.png")
                img = QImage(path)
                if img.isNull() or not img.save(dp, "PNG"):
                    raise ValueError("The image could not be read.")
            elif ext in WORD_EXT:
                dp = os.path.join(self.tmpdir, base + "_view.pdf")
                docx_to_pdf(path, dp)
            elif ext in EXCEL_EXT:
                dp = os.path.join(self.tmpdir, base + "_view.pdf")
                excel_to_pdf(path, dp)
            elif ext in (".doc", ".xls"):
                raise ValueError("Old .doc/.xls files are not supported. Please save the file "
                                 "as .docx / .xlsx first.")
            else:
                raise ValueError(f"Unsupported file type: {ext or 'unknown'}")
            new = fitz.open(dp)
            pw = None
            if new.needs_pass:
                QApplication.restoreOverrideCursor()
                pw, ok = QInputDialog.getText(self, APP_NAME, "This PDF is password protected.\nPassword:",
                                              QLineEdit.EchoMode.Password)
                QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
                if not ok or not new.authenticate(pw):
                    new.close()
                    raise ValueError("Incorrect password or cancelled.")
            if new.page_count == 0:
                new.close()
                raise ValueError("The document has no pages.")
        except Exception as exc:                 # noqa
            QApplication.restoreOverrideCursor()
            self.error(f"Could not open the file:\n{path}\n\n{exc}", "Open failed")
            return
        QApplication.restoreOverrideCursor()
        if self.doc is not None:
            self.doc.close()
        self.doc, self.doc_path, self.src_path, self.password = new, dp, path, pw
        self.last_dir = str(Path(path).parent)
        self.page, self.zoom = 0, 1.0
        self.results, self.meta = [], {}
        self.out_text.clear()
        self.orig_text.clear()
        self._close_preview()
        self.btn_save.setEnabled(False)
        self.btn_translate.setEnabled(True)
        self.view.setStyleSheet("")
        self.scroll.setWidgetResizable(False)
        n = self.doc.page_count
        self.spin.blockSignals(True)
        self.spin.setRange(1, n)
        self.spin.setSuffix(f"/{n}")
        self.spin.setValue(1)
        self.spin.blockSignals(False)
        self._set_nav_enabled(True)
        self.setWindowTitle(f"{APP_NAME} - {Path(path).name}")
        self.render_page()
        self.fit_width()
        self.info(f"Opened {Path(path).name} ({n} page{'s' if n != 1 else ''})")

    # ---- viewing --------------------------------------------------------
    def render_page(self):
        if self.doc is None:
            return
        try:
            page = self.doc[self.page]
            s = BASE_SCALE * self.zoom
            pix = page.get_pixmap(matrix=fitz.Matrix(s, s), alpha=False)
            img = QImage(pix.samples, pix.width, pix.height, pix.stride,
                         QImage.Format.Format_RGB888)
            pm = QPixmap.fromImage(img.copy())
        except Exception as exc:                 # noqa
            self.error(f"Could not display page {self.page + 1}:\n{exc}")
            return
        self.view.clear_selection()
        self.view.setPixmap(pm)
        self.view.setFixedSize(pm.size())
        self.zoom_lbl.setText(f"{int(round(self.zoom * 100))}%")
        self.spin.blockSignals(True)
        self.spin.setValue(self.page + 1)
        self.spin.blockSignals(False)
        self.btn_prev.setEnabled(self.page > 0)
        self.btn_next.setEnabled(self.page < self.doc.page_count - 1)
        self.on_selection()
        self.render_translated()

    def _close_preview(self):
        self._preview_n += 1                     # ignores any preview still being built
        if self.tdoc is not None:
            try:
                self.tdoc.close()
            except Exception:                    # noqa
                pass
            self.tdoc = None
        self.tview.clear()
        self.tview.setMinimumSize(0, 0)
        self.tview.setMaximumSize(16777215, 16777215)
        self.tview.setText("The translated document will appear here,\n"
                           "in the same layout as the original.")
        self.tscroll.setWidgetResizable(True)

    def render_translated(self):
        if self.tdoc is None or self.page >= self.tdoc.page_count:
            return
        try:
            s = BASE_SCALE * self.zoom
            pix = self.tdoc[self.page].get_pixmap(matrix=fitz.Matrix(s, s), alpha=False)
            img = QImage(pix.samples, pix.width, pix.height, pix.stride,
                         QImage.Format.Format_RGB888)
            pm = QPixmap.fromImage(img.copy())
        except Exception:                        # noqa
            return
        self.tscroll.setWidgetResizable(False)
        self.tview.setPixmap(pm)
        self.tview.setFixedSize(pm.size())

    def _start_preview(self, results):
        self._close_preview()
        token = self._preview_n
        dst = os.path.join(self.tmpdir, f"preview_{token}.pdf")
        src, pw = self.doc_path, self.password

        def fn():
            build_layout_pdf(src, pw, results, dst, watermark=False)
            return dst
        self.statusBar().showMessage("Building the translated document view ...")
        self.run_task(fn, lambda d, t=token: self._preview_ready(d, t),
                      lambda m, t=token: self._preview_failed(m, t))

    def _preview_ready(self, path, token):
        if token != self._preview_n:
            return
        try:
            self.tdoc = fitz.open(path)
        except Exception as exc:                 # noqa
            self._preview_failed(str(exc), token)
            return
        self.render_translated()
        self.tabs.setCurrentIndex(0)
        self.info(f"Done: {self.meta.get('src_name', '')} -> {self.meta.get('tgt_name', '')}. "
                  "Use 'Save translation as ...' to store it as a new file.")

    def _preview_failed(self, msg, token):
        if token != self._preview_n:
            return
        self.tabs.setCurrentIndex(1)
        self.info("The layout view could not be built (" + msg + "). The translated text is shown instead.")

    def go_to(self, idx):
        if self.doc is None:
            return
        idx = max(0, min(idx, self.doc.page_count - 1))
        self.page = idx
        self.render_page()
        self.scroll.verticalScrollBar().setValue(0)

    def prev_page(self):
        self.go_to(self.page - 1)

    def next_page(self):
        self.go_to(self.page + 1)

    def set_zoom(self, z):
        if self.doc is None:
            return
        self.zoom = max(MIN_ZOOM, min(MAX_ZOOM, z))
        self.render_page()

    def zoom_in(self):
        self.set_zoom(self.zoom + 0.25)

    def zoom_out(self):
        self.set_zoom(self.zoom - 0.25)

    def fit_width(self):
        if self.doc is None:
            return
        avail = self.scroll.viewport().width() - 24
        pw = self.doc[self.page].rect.width
        if pw > 0 and avail > 100:
            self.set_zoom(avail / (pw * BASE_SCALE))

    def clear_selection(self):
        self.view.clear_selection()
        self.on_selection()

    def on_selection(self):
        if self.doc is None:
            self.sel_lbl.setText("No document open")
        elif self.view.sel is not None:
            self.sel_lbl.setText(f"Area selected on page {self.page + 1} - only this area will be translated")
        else:
            self.sel_lbl.setText("No selection - the complete document will be translated "
                                 "(drag on the page to select an area)")

    # ---- translating ----------------------------------------------------
    def start_translate(self):
        if self.doc is None or self.worker is not None:
            return
        tgt = self.tgt_combo.currentData()
        src = self.src_combo.currentData()
        sel = self.view.sel
        if sel is not None:
            s = BASE_SCALE * self.zoom
            rect = fitz.Rect(sel.left() / s, sel.top() / s, sel.right() / s, sel.bottom() / s)
            jobs = [(self.page, rect)]
        else:
            n = self.doc.page_count
            if n > 60:
                ans = QMessageBox.question(
                    self, APP_NAME, f"This document has {n} pages. Translating all of them may take "
                    "a while.\nTip: you can also select an area. Continue?")
                if ans != QMessageBox.StandardButton.Yes:
                    return
            jobs = [(p, None) for p in range(n)]
        self.worker = TranslateWorker(self.doc_path, self.password, jobs, src, tgt)
        self.worker.ask_download.connect(self.on_ask_download)
        self.worker.progress.connect(self.on_progress)
        self.worker.finished_ok.connect(self.on_translated)
        self.worker.failed.connect(self.on_failed)
        self.worker.finished.connect(self.on_worker_finished)
        self._set_busy(True)
        self.worker.start()

    def _set_busy(self, busy):
        self.btn_translate.setVisible(not busy)
        self.btn_cancel.setVisible(busy)
        self.progress.setVisible(busy)
        for w in (self.btn_open, self.btn_save, self.src_combo, self.tgt_combo):
            w.setEnabled(not busy)
        if busy:
            self.progress.setRange(0, 0)
            self.statusBar().showMessage("Working ... (first run may take a moment to load the engine)")
        else:
            self.btn_save.setEnabled(bool(self.results))

    def offer_bundle(self):
        """First launch only: offer to prepare the standard language set."""
        flag = FLAG_DIR / "packs_prompted.flag"
        if flag.exists():
            return
        try:
            FLAG_DIR.mkdir(parents=True, exist_ok=True)
            flag.write_text("ok", encoding="utf-8")
        except OSError:
            pass
        try:
            if any(LOCAL_PACK_DIR.glob("*.argosmodel")):
                return                           # packs already supplied with the program
        except OSError:
            pass
        names = ", ".join(LANG_NAMES[c] for c in BUNDLE_CODES)
        ans = QMessageBox.question(
            self, APP_NAME,
            f"Prepare offline translation now?\n\nLanguages: {names} (each to and from English).\n\n"
            "This downloads the language models ONCE (several hundred MB; model files only - "
            "your documents are never sent anywhere). Afterwards everything works fully offline.\n\n"
            "You can skip this; packs are also requested automatically when first needed.")
        if ans != QMessageBox.StandardButton.Yes:
            return
        self.statusBar().showMessage("Downloading language packs - please wait ...")
        self.run_task(prepare_packs, self._bundle_done, self._bundle_failed)

    def _bundle_done(self, missing):
        self.refresh_languages()
        extra = f" Not available: {', '.join(missing)}." if missing else ""
        self.info("Language packs are ready for offline use." + extra)

    def _bundle_failed(self, msg):
        self.error("The language packs could not be downloaded (no internet?).\n"
                   "They will be requested again when needed.\n\n" + msg, "Language packs")

    def on_ask_download(self, names):
        ans = QMessageBox.question(
            self, APP_NAME,
            f"To translate this document the app needs this language pack:\n\n    {names}\n\n"
            "It will be downloaded ONCE (the language model only - your document and text "
            "are never sent anywhere) and afterwards works fully offline.\n\nDownload now?")
        w = self.worker
        if w is not None:
            w.answer(ans == QMessageBox.StandardButton.Yes)

    def cancel_translate(self):
        if self.worker is not None:
            self.worker.cancel()
            self.btn_cancel.setEnabled(False)

    def on_progress(self, done, total, msg):
        self.progress.setRange(0, max(total, 1))
        self.progress.setValue(done)
        self.statusBar().showMessage(msg)

    def on_worker_finished(self):
        self.worker = None
        self.btn_cancel.setEnabled(True)
        self._set_busy(False)

    def on_failed(self, msg):
        self.statusBar().showMessage("Stopped")
        if msg != "Translation cancelled.":
            self.error(msg, "Translation failed")
        else:
            self.info(msg)

    def on_translated(self, results, meta):
        self.results, self.meta = results, meta
        sep = "\n"
        self.out_text.setPlainText(self._compose(results, "translated", sep))
        self.orig_text.setPlainText(self._compose(results, "original", sep))
        self.tabs.setCurrentIndex(1)
        self.btn_save.setEnabled(True)
        self._start_preview(results)

    @staticmethod
    def _compose(results, key, sep):
        blocks = []
        for r in results:
            blocks.append(f"=== Page {r['page']} ===\n" + sep.join(r[key]))
        return "\n\n".join(blocks)

    # ---- saving ---------------------------------------------------------
    def save_translation(self):
        if not self.results:
            QMessageBox.information(self, APP_NAME, "Nothing to save yet - translate first.")
            return
        stem = Path(self.src_path).stem
        suggested = str(Path(self.src_path).parent / f"{stem}_translated_{self.meta.get('tgt_code', '')}.pdf")
        flt = ("Translated PDF - original layout (*.pdf);;"
               "Word document - text only (*.docx);;Text file (*.txt)")
        path, chosen = QFileDialog.getSaveFileName(self, "Save translation as a new file", suggested, flt)
        if not path:
            return
        ext = Path(path).suffix.lower()
        if ext not in (".docx", ".pdf", ".txt"):
            ext = {"Translated": ".pdf", "Word": ".docx", "Text": ".txt"}[chosen.split()[0]]
            path += ext
        try:
            same = [self.src_path, self.doc_path]
            if os.path.exists(path) and any(os.path.samefile(path, q) for q in same):
                self.error("The original file cannot be overwritten.\nPlease choose a different "
                           "file name for the translation.", "Save blocked")
                return
            sep = "\n"
            title = f"{stem} - translated to {self.meta.get('tgt_name', '')}"
            if ext == ".docx":
                import docx
                from docx.shared import Pt, RGBColor
                from docx.enum.text import WD_ALIGN_PARAGRAPH
                d = docx.Document()
                hp = d.sections[0].header.paragraphs[0]       # printed on every page
                hp.alignment = WD_ALIGN_PARAGRAPH.CENTER
                run = hp.add_run(WATERMARK_TEXT)
                run.bold = True
                run.font.size = Pt(18)
                run.font.color.rgb = RGBColor(0xD3, 0x2F, 0x2F)
                d.add_heading(title, 1)
                for r in self.results:
                    d.add_heading(f"Page {r['page']}", 2)
                    for p in r["translated"]:
                        d.add_paragraph(p)
                d.save(path)
            elif ext == ".pdf":
                QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
                try:
                    build_layout_pdf(self.doc_path, self.password, self.results, path, watermark=True)
                finally:
                    QApplication.restoreOverrideCursor()
            else:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(f"*** {WATERMARK_TEXT} ***\n\n" + title + "\n\n"
                             + self._compose(self.results, "translated", sep)
                             + f"\n\n*** {WATERMARK_TEXT} ***\n")
        except PermissionError:
            self.error("Permission denied. The file may be open in another program, or the "
                       "folder is protected.\nPlease choose another location.", "Save failed")
            return
        except Exception as exc:                 # noqa
            self.error(f"The file could not be saved:\n{exc}", "Save failed")
            return
        self.info(f"Saved: {path}")
        QMessageBox.information(self, APP_NAME, f"Translation saved as a new file:\n{path}\n\n"
                                f"It carries the watermark '{WATERMARK_TEXT}'.\n"
                                "Your original document was not changed.")

    # ---- closing --------------------------------------------------------
    def closeEvent(self, e):
        if self.worker is not None:
            self.worker.cancel()
            self.worker.wait(3000)
        try:
            if self.doc is not None:
                self.doc.close()
        except Exception:                        # noqa
            pass
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        e.accept()


# --------------------------------------------------------------------------
# 10. Start-up
# --------------------------------------------------------------------------
def main():
    if "--download-packs" in sys.argv:           # console mode: prepare the packs and exit
        try:
            miss = prepare_packs()
            print("\nDone. Pack files are in:", LOCAL_PACK_DIR)
            if miss:
                print("Not available in the index:", ", ".join(miss))
        except Exception as exc:                 # noqa
            print("Could not download the language packs:", exc)
        return
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyleSheet(STYLESHEET)

    def hook(etype, value, tb):
        traceback.print_exception(etype, value, tb)
        try:
            QMessageBox.critical(None, APP_NAME, f"An unexpected error occurred:\n{value}")
        except Exception:                        # noqa
            pass
    sys.excepthook = hook

    win = MainWindow()
    win.show()
    QTimer.singleShot(700, win.offer_bundle)
    app.exec()


if __name__ == "__main__":
    main()
