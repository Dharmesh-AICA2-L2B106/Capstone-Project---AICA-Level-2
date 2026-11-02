"""Builds "PDF Play Station 2.0 - Development Documentation.docx" in the project folder.

The document's content lives in this script so it can be rebuilt and extended at
every build stage:   .venv\\Scripts\\python.exe docs\\build_dev_document.py
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor, Cm

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import APP_NAME, APP_VERSION, APP_STAGE, APP_BYLINE, OFFLINE_NOTE   # noqa: E402
from app.catalog import SECTIONS                                             # noqa: E402

OUT = ROOT / "PDF Play Station 2.0 - Development Documentation.docx"
NAVY = RGBColor(0x0B, 0x1E, 0x3D)
GOLD = RGBColor(0x6F, 0x5A, 0x3F)


# ------------------------------------------------------------------ helpers

def shade(cell, hex_fill: str) -> None:
    tc = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_fill)
    tc.append(shd)


def table(doc, header: list[str], rows: list[list[str]], widths: list[float] | None = None) -> None:
    t = doc.add_table(rows=1, cols=len(header))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, h in enumerate(header):
        c = t.rows[0].cells[i]
        c.text = ""
        run = c.paragraphs[0].add_run(h)
        run.bold = True
        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        shade(c, "0B1E3D")
    for row in rows:
        cells = t.add_row().cells
        for i, v in enumerate(row):
            cells[i].text = v
    if widths:
        for row in t.rows:
            for i, w in enumerate(widths):
                row.cells[i].width = Cm(w)
    for row in t.rows:
        for c in row.cells:
            for p in c.paragraphs:
                for r in p.runs:
                    r.font.size = Pt(9.5)
    doc.add_paragraph()


def bullets(doc, items: list[str], style: str = "List Bullet") -> None:
    for it in items:
        doc.add_paragraph(it, style=style)


def para(doc, text: str, bold_lead: str = "") -> None:
    p = doc.add_paragraph()
    if bold_lead:
        p.add_run(bold_lead).bold = True
    p.add_run(text)


# ------------------------------------------------------------------ content

def build() -> Path:
    doc = Document()
    st = doc.styles["Normal"]
    st.font.name = "Segoe UI"
    st.font.size = Pt(10.5)
    for name, size in (("Heading 1", 16), ("Heading 2", 13), ("Heading 3", 11.5)):
        h = doc.styles[name]
        h.font.name = "Georgia"
        h.font.size = Pt(size)
        h.font.color.rgb = NAVY
    for s in doc.sections:
        s.left_margin = s.right_margin = Cm(2.2)
        s.top_margin = s.bottom_margin = Cm(2)
        fp = s.footer.paragraphs[0]
        fp.text = f"{APP_NAME} {APP_VERSION} - Development Documentation  |  {OFFLINE_NOTE}"
        fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        fp.runs[0].font.size = Pt(8)

    # ---- title page
    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = title.add_run(f"\n\n{APP_NAME} 2.0")
    r.font.size = Pt(30)
    r.font.name = "Georgia"
    r.font.color.rgb = NAVY
    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = sub.add_run("Development Documentation")
    r.font.size = Pt(16)
    r.font.color.rgb = GOLD
    by = doc.add_paragraph()
    by.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = by.add_run(APP_BYLINE)
    r.italic = True
    r.font.size = Pt(12)
    meta = doc.add_paragraph()
    meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
    meta.add_run(f"\nVersion {APP_VERSION}  ·  {APP_STAGE}\n"
                 f"Document generated {dt.date.today():%d %B %Y}\n\n{OFFLINE_NOTE}")
    doc.add_page_break()

    # ---- 1 purpose
    doc.add_heading("1. Purpose and scope", 1)
    para(doc, "PDF Play Station 2.0 brings three groups of tools into one offline Windows desktop "
              "application for internal use at the firm:")
    bullets(doc, ["PDF & Document Utilities - merge, split, extract, number, rearrange and rotate pages, "
                  "images, passwords and Markdown;",
                  "Convert to Excel / Word - tables and text into editable Office files, including the "
                  "balance-checked bank-statement mode;",
                  "Secure Redaction - permanent removal of confidential data with proof that it is gone."])
    para(doc, "It replaces two separate tools - the earlier PDF Play Station (v1.1.0, PyQt5 single file) and "
              "PDF Converter Pro - without changing either of them. Both remain where they are; code is "
              "only read from them and re-used in this new project.")
    doc.add_heading("Guiding principles", 2)
    bullets(doc, [
        "100% offline: no document, text or result ever leaves the computer. Internet is used once, "
        "only to install components.",
        "Accuracy over convenience: figures are verified (bank balances, redaction checks) and anything "
        "doubtful is flagged rather than guessed.",
        "Originals are never changed; outputs are new files and are never overwritten silently.",
        "Simple screens: every tool uses the same three steps - Add files, Choose options, Run.",
        "Performance: tools load only when first opened; heavy work runs in the background so the "
        "screen never freezes.",
    ])

    # ---- 2 decisions
    doc.add_heading("2. Key decisions (record)", 1)
    table(doc, ["Date", "Decision", "Reason"], [
        ["29-10-2026", "Build a new project in E:\\PDF Play Station 2.0", "Keep the existing tools intact; "
         "E: is outside OneDrive, so builds and installs are not slowed or locked by syncing."],
        ["29-10-2026", "Internal firm use only - keep PyMuPDF (AGPL)", "Best true-redaction engine; AGPL "
         "obligations apply on distribution outside the firm, which is not planned."],
        ["29-10-2026", "Screens in PySide6 (Qt 6, LGPL) instead of PyQt5", "PDF Converter Pro already uses "
         "PySide6 and two Qt versions cannot share one window; LGPL is also less restrictive than GPL."],
        ["29-10-2026", "Deliver as Python (.py + run.bat) first; EXE after finalisation",
         "Minor changes are easier to make and test in Python source."],
        ["29-10-2026", "Add Rotate PDF (all / selected / odd / even / sideways)", "Requested; sideways pages "
         "detected offline with Tesseract's orientation data."],
        ["29-10-2026", "Smart Redaction categories: PAN, Aadhaar, GSTIN, TAN, CIN, DIN, bank account, IFSC, "
         "passport, voter ID, mobile, e-mail, date of birth", "Requested; names and addresses stay manual "
         "because they cannot be detected reliably offline."],
        ["29-10-2026", "OCR redaction for scanned PDFs in English, Hindi and Marathi", "The earlier tool "
         "could not find or verify text inside scans."],
        ["29-10-2026", "Readable highlight in all dropdowns, lists and menus", "Known bug in the earlier "
         "tool: the highlighted dropdown item was navy text on navy."],
        ["29-10-2026", "Heavy jobs (OCR, orientation checks) in a separate worker process; light jobs in a "
         "background thread", "The window never freezes; a crash or a huge file in the worker cannot close the "
         "application; Cancel can stop the worker outright."],
        ["29-10-2026", "Sideways detection: text direction for pages with text, Tesseract only for scans",
         "Text direction is exact and instant; OCR is slower and is used only where there is no text layer."],
        ["29-10-2026", "Outputs are always new files with a suffix (e.g. _rotated); an existing name gets "
         "' (2)'", "Originals are never changed and nothing is overwritten without asking."],
        ["29-10-2026", "Passwords asked per protected PDF, kept in memory for the session only",
         "Never written to disk, settings or logs (DPDP)."],
        ["29-10-2026", "A batch continues when one file fails; the failure is reported",
         "One damaged PDF should not stop a batch of fifty."],
        ["29-10-2026", "Section 2 uses PDF Converter Pro's engine copied unchanged into app/convert",
         "It is proven (98 tests, real-scan accuracy measured); rewriting it would risk the figures. Only the "
         "package header, a reduced config.py and test import paths were adapted."],
        ["29-10-2026", "Conversion OCR language defaults to English",
         "English OCR reads figures most reliably; Hindi / Marathi can be chosen per run."],
        ["29-10-2026", "Manual, Find, Smart, Review and Apply are one workspace (one document, one list of "
         "marked areas) reached from five sidebar entries", "Users mark from several sources and review "
         "everything once; switching tools never loses work."],
        ["29-10-2026", "Redaction OCR defaults to English + Hindi + Marathi", "Names may be written in "
         "Devanagari; tested: numbers and PAN read identically with all three languages."],
        ["29-10-2026", "New check: every redacted area must be solid black in the saved file",
         "Proves visually that nothing in the area is still shown, independent of the text checks."],
        ["29-10-2026", "Low-confidence detections (format only, no keyword) are listed but not ticked",
         "Avoids removing invoice numbers or dates that only look like an ID."],
    ], [2.3, 6.2, 8.0])

    # ---- 3 architecture
    doc.add_heading("3. Architecture", 1)
    para(doc, "The application is a Python package with a thin start file. Screens (UI) and processing "
              "(services) are kept apart, so a tool's engine can be tested and improved without touching "
              "its screen.")
    table(doc, ["Layer", "Responsibility"], [
        ["PDF_Play_Station.py", "Start file: logging, theme, main window; --version."],
        ["app/shell.py", "Main window: header with name and byline, sidebar, page area, footer with the "
                         "offline statement; remembers window size."],
        ["app/sidebar.py", "Search box and three sliding (accordion) sections - opening one closes the other."],
        ["app/catalog.py", "Single list of sections, tools and their options. Adding a tool here adds it to "
                           "the sidebar, search and home page."],
        ["app/pages.py", "Home page and the one tool-page template: file list (with Up/Down/Sort where order "
                         "matters), options, password prompts, progress bar with Cancel, result panel with "
                         "Open folder, and the confirmation dialog for plans such as sideways pages."],
        ["app/workspace.py", "Rearrange Pages workspace: page thumbnails to drag, rotate, remove or reverse."],
        ["app/runners.py", "Connects each tool to its engine: reads the on-screen options, names the output "
                           "files, processes a batch file by file and collects results and errors."],
        ["app/theme.py", "Colours from kirtanepandit.com, stylesheet and palette (readable highlights)."],
        ["app/icons.py", "Line icons drawn from SVG at runtime - no image files to manage."],
        ["app/logger.py", "Local rotating log in logs\\; never records document text or passwords."],
        ["app/services/common.py", "Shared engine helpers: page-range parsing (1, 3-5, 8-end), safe opening "
                                   "of protected PDFs, atomic saving (temporary file, then rename), output names "
                                   "that never overwrite, progress and cancel (Job), results (Result)."],
        ["app/services/utilities.py", "Section 1 engines: merge, split, extract, page numbers, rearrange, "
                                      "rotate and sideways detection, PDF to images, images to PDF, protect, "
                                      "remove password."],
        ["app/services/markdown_pdf.py", "Markdown to PDF (safe HTML, local fonts and images) and PDF to "
                                         "Markdown (headings, lists, tables, links, images, OCR for scans)."],
        ["app/services/ocr.py", "Finds Tesseract, checks language data, page text and page orientation."],
        ["app/services/redaction.py", "Section 3 engine: detection of 13 categories, Find, OCR word "
                                      "positions for scans, true redaction (ported), verification (ported + "
                                      "black-out and OCR checks) and the stand-alone inspection."],
        ["app/redaction_ui.py", "Redaction workspace: page viewer with drawing/moving/resizing boxes, undo, the "
                                "five panels (Mark, Find, Smart detect, Review, Apply) and the summary dialog."],
        ["app/convert/", "Section 2 engine copied from PDF Converter Pro 1.0.0: pdf_inspector (page types), "
                         "extractor + layout + table_extractor (text, tables up to 20+ columns, reading order, "
                         "OCR), cell_values (Indian numbers, dates, PAN/GSTIN kept as text), pdf_to_excel, "
                         "pdf_to_word, bank_statement + statement_excel (balance-checked statements), batch, "
                         "output_manager (atomic save + re-open check), validators, ocr_engine."],
        ["app/jobs.py", "Job runner: light jobs in a background thread; heavy jobs (OCR, orientation checks) "
                        "in a separate worker process, with progress and Cancel."],
    ], [4.5, 12.0])

    # ---- 4 components
    doc.add_heading("4. Components and licences", 1)
    table(doc, ["Component", "Version", "Used for", "Licence"], [
        ["Python", "3.14 (64-bit)", "Language", "PSF"],
        ["PySide6-Essentials", "6.12.0", "Screens", "LGPL-3.0"],
        ["PyMuPDF", "1.28.2 (kept < 2.0)", "Utilities, page viewer, redaction", "AGPL-3.0 (internal use)"],
        ["pdfplumber / pdfminer.six", "0.11.10", "Text and table extraction (Excel/Word)", "MIT"],
        ["pypdfium2", "5.14.0", "Page rendering for conversion and OCR", "Apache-2.0 / BSD"],
        ["openpyxl", "3.1.5", "Excel output", "MIT"],
        ["python-docx / lxml", "1.2.0 / 6.1.3", "Word output", "MIT / BSD"],
        ["Pillow", "13.0.0", "Images", "MIT-CMU"],
        ["pytesseract + Tesseract OCR", "0.3.13 + 5.4.0", "OCR (eng, hin, mar - tessdata_best; osd)",
         "Apache-2.0"],
        ["Markdown", "3.11", "Markdown to PDF", "BSD"],
        ["pytest / reportlab", "9.1.1 / 5.1.0", "Automated tests only", "MIT / BSD"],
    ], [4.2, 3.2, 5.6, 3.5])
    para(doc, "Why PyMuPDF is kept below 2.0: ", "")
    doc.paragraphs[-1].runs[0].bold = True
    doc.paragraphs[-1].add_run("the earlier tool established that PyMuPDF 2.0 moves the text that follows a "
                               "redacted word. A built-in engine self-test (carried over) refuses to "
                               "redact if the installed engine shows this fault.")

    # ---- 5 tools
    doc.add_heading("5. Tool catalogue", 1)
    for s in SECTIONS:
        doc.add_heading(s.name, 2)
        rows = []
        for t in s.tools:
            opts = "; ".join(o.label + (f" ({', '.join(o.choices)})" if o.choices and o.kind != "checks" else "")
                             for o in t.options if o.label)
            rows.append([t.name, t.summary, opts or "-", "Connected" if t.ready else "Planned"])
        table(doc, ["Tool", "What it does", "Options", "Status"], rows, [3.3, 5.0, 6.4, 1.8])

    doc.add_heading("Rotate PDF - behaviour", 3)
    bullets(doc, [
        "All pages / Odd pages only / Even pages only: every matching page is turned by the chosen "
        "direction (90° clockwise, 90° anticlockwise or 180°).",
        "Selected pages: page numbers typed as a list, e.g. 2, 5-7, 10; the Page numbers box is only active "
        "for this choice.",
        "Sideways pages (detected automatically): for a page with a text layer, the writing direction of its "
        "text (weighted by characters, at least 60% agreeing) gives the exact turn needed; for a scanned page "
        "without text, the page is rendered at 150 dpi and Tesseract's orientation check (osd) decides. "
        "Pages found sideways or upside down are listed with the proposed turn and the method used, and "
        "nothing is saved until the user clicks Rotate pages. Pages that cannot be decided (too little "
        "text) are listed and left unchanged. Direction is not needed and is disabled.",
        "Checked facts behind the method: PyMuPDF reports text direction in unrotated page space, so text at "
        "angle t reads upright when the page's /Rotate equals t; Tesseract's osd 'rotate' value is the "
        "clockwise turn that makes the image upright (a page shown 90° clockwise returns 270).",
        "Rotation changes the page's /Rotate setting - content is not re-drawn, so quality is unchanged; "
        "a turn is added to any rotation the page already has.",
    ])

    doc.add_heading("Other Section 1 tools - behaviour", 3)
    bullets(doc, [
        "Merge PDF: files are merged in the list order (Up / Down / Sort A-Z, where 2 sorts before 10); one "
        "bookmark per original file, with the originals' own bookmarks nested under it.",
        "Split PDF: every N pages, by page ranges (one file per range, e.g. 1-3, 4-10) or every page; files "
        "named name_p1-3.pdf etc.",
        "Extract Pages: pages in the order typed (e.g. 3, 1, 5-end).",
        "Page Numbering: six positions, four formats (1, Page 1, Page 1 of N, 1 / N), start number, font size "
        "and a page list; the number is a running number over the chosen pages and stays upright on rotated "
        "pages.",
        "Rearrange Pages: thumbnails to drag; rotate left/right, remove, reverse, reset; the status line "
        "summarises the changes before saving.",
        "PDF to Images: PNG or JPEG at 150/200/300 dpi for the chosen pages.",
        "Images to PDF: A4, Letter or page = image size; orientation automatic, portrait or landscape; phone "
        "photos are turned upright from their EXIF data; every page of a multi-page TIFF is included.",
        "Password Protect PDF: AES-256; Allow printing / copying / editing; an optional separate permissions "
        "password (without it, restrictions use a random owner password and the user is told they cannot be "
        "lifted later); the output is re-opened with the password to verify it.",
        "Remove PDF Password: uses a known password only. With the owner password all security is removed; "
        "with only the open password, the open password is removed and restrictions are kept.",
        "Markdown to PDF: page size, orientation, font, font size, page numbers, title, header and footer; "
        "unsafe HTML is removed; remote images are never downloaded; Hindi and Marathi text is supported.",
        "PDF to Markdown: headings from font size, bold/italic/code, lists, tables, links, images saved to "
        "a folder next to the .md, repeated headers/footers removed, optional page markers; scanned pages "
        "are read with OCR (English/Hindi/Marathi) and flagged for checking.",
    ])

    doc.add_heading("Convert to Excel / Word - behaviour", 3)
    bullets(doc, [
        "PDF to Excel: one workbook per PDF next to the original (or in the chosen folder), or one combined "
        "workbook with a sheet per PDF; tables combined across pages, one sheet per table or one per page; "
        "numbers stored as real numbers with the Indian format (1,00,000); leading zeros, PAN, GSTIN and long "
        "account numbers kept as text; dates read day-first; text that starts with '=' is never turned into "
        "a formula.",
        "PDF to Word: editable document (headings, lists, tables), layout-preserving, or plain text "
        "extraction; wide tables (10+ columns) get smaller cell fonts so they fit the page.",
        "Scanned pages are found automatically and read with Tesseract (English by default; Hindi / Marathi "
        "available); the result panel says how many pages were read with OCR.",
        "Bank Statement to Excel: columns are found from the header; amounts are read with a digits-only OCR "
        "pass; every row is reconciled with the running balance (chain of trust). Doubtful cells are re-read "
        "at 400 dpi; values are inferred only when the next row confirms them; the bank's printed totals are "
        "compared; dates are validated. Each row carries a status - OK, Re-read, Corrected, Inferred or Check "
        "- and the workbook has Statement, Review, Bank Totals Check and Notes sheets.",
        "Measured on 29-10-2026 inside PDF Play Station (same as in PDF Converter Pro): Savings Bank Account "
        "scan 31 of 32 rows exact, 1 flagged; UCCA statement (degraded 200 dpi rebuild) 243 of 251 exact, 8 "
        "flagged; in both, no wrong figure was left unflagged.",
        "Password-protected PDFs use the password typed on the tool page; the engine never keeps it after "
        "reading the file.",
    ])

    doc.add_heading("Secure Redaction - behaviour", 3)
    bullets(doc, [
        "One workspace, five steps: Mark (draw boxes), Find (search terms, one per line), Smart detect, Review "
        "(tick / untick every area, click to see it) and Apply. The step buttons above the page and the five "
        "sidebar entries switch between them; the open PDF and the marked areas stay. Undo (Ctrl+Z) covers "
        "every change.",
        "Smart detect - 13 categories, offline, each with a confidence and the reason: PAN (holder type from "
        "the 4th character), Aadhaar (Verhoeff check digit), GSTIN (official check character), TAN, CIN "
        "(company-type code), DIN (only next to 'DIN'), bank account (only next to 'A/c No.' or similar by "
        "default), IFSC, passport (High only next to 'passport'), voter ID / EPIC, mobile, e-mail, date of "
        "birth (only next to DOB / date of birth / जन्म). High and Medium are ticked; Low is listed for a look. "
        "A PAN inside a GSTIN is not listed twice.",
        "Scanned pages: Tesseract reads the page at 300 dpi and returns every word with its position; the "
        "word box is shared across its letters, so Find and Smart detect mark scans exactly like text pages. "
        "OCR is done once per page and re-used by later searches in the same session.",
        "Apply (method unchanged from the earlier tool): annotations, form fields and links in the areas are "
        "deleted; text, image pixels and drawings inside are removed from the page; only the area is replaced "
        "by an image patch from a snapshot (all areas blacked out), so the rest of the page stays searchable; "
        "a page that cannot be cleaned selectively is flattened and reported. Bookmarks containing a "
        "redacted value become [REDACTED]; metadata, XMP, JavaScript, attachments and thumbnails are removed; "
        "the file is written as one full revision. The original is never changed and the engine self-test "
        "must pass first.",
        "Verification after saving: output opens; page count; no text inside any area; every area solid "
        "black; no annotations or fields left in areas; redacted values not extractable anywhere (or reported "
        "if they still appear where they were not marked); metadata and bookmarks; revisions; JavaScript; "
        "embedded files; metadata; and, for scanned pages, an OCR read proving the values can no longer be "
        "read. 'Verify in detail…' opens Verify Redacted PDF with the file and values filled in.",
        "Verify Redacted PDF (stand-alone, any PDF): looks for the given values in text, annotations, "
        "metadata, bookmarks and - with OCR - scanned pages, plus the structure checks; values are shown "
        "masked (AB••••••4Q).",
    ])

    # ---- 6 earlier tool review
    doc.add_heading("6. Review of the earlier PDF Play Station (v1.1.0)", 1)
    para(doc, "The earlier tool (one 4,644-line PyQt5 file) was studied read-only on 29-10-2026.")
    doc.add_heading("Carried over", 2)
    bullets(doc, [
        "True redaction: content inside marked areas is removed from the PDF, not covered; only the "
        "affected areas are rasterised; whole-page flattening is the fallback if removal is not clean.",
        "Removal of annotations, form fields and links touching a redacted area; metadata, XMP, JavaScript, "
        "attachments and thumbnails scrubbed; saved as a single full rewrite (no recoverable revisions).",
        "Automatic verification of the redacted output and a stand-alone Verify Redacted PDF tool.",
        "Aadhaar detection with the Verhoeff check digit; PAN holder-type check (4th character).",
        "AES-256 password protection with verification; password removal only with a known password.",
        "Markdown to PDF with an HTML whitelist (no scripts, local images only).",
    ])
    doc.add_heading("Improved in 2.0", 2)
    bullets(doc, [
        "OCR (English, Hindi, Marathi) so scanned pages can be searched, redacted and verified.",
        "Eight more Smart Redaction categories.",
        "Rotate PDF added.",
        "No runtime pip installer: components are installed once by run.bat; the application itself never "
        "connects to the internet.",
        "Readable highlight in dropdowns, lists and menus (known bug).",
        "Split into modules with automated tests instead of one large file.",
        "Batch processing for most utilities (several PDFs at once), with one failed file not stopping the "
        "rest.",
        "Images to PDF: EXIF orientation and multi-page TIFF; Markdown to PDF: Hindi / Marathi text.",
        "PDF to Markdown: OCR for scanned pages.",
        "Heavy work in a separate worker process with Cancel.",
    ])

    # ---- 7 UI
    doc.add_heading("7. Screen design", 1)
    bullets(doc, [
        "Header: application name, byline 'by CA Aditya Mundada', section tagline.",
        "Left: search box, Home, and three sliding sections (one open at a time).",
        "Each tool page: breadcrumb, title, one-line description, three step chips, Files card (or page "
        "workspace), Options card, and a run bar with the action button.",
        "Footer: version and stage, Help, About, and '100% Offline | Stay safe from DPDP Implications' at "
        "the bottom right.",
        "Colours: navy #0B1E3D, gold #B8966E, cream #F7F5F0 and white, from kirtanepandit.com.",
        "Highlight rule: selected or hovered items in dropdowns, lists and menus use light cream-gold "
        "#EADFCC with navy text - set both in the stylesheet and in the application palette, because some "
        "Qt pop-ups take their colours from the palette.",
    ])

    # ---- 8 build stages
    doc.add_heading("8. Build stages and progress log", 1)
    table(doc, ["Stage", "Content", "Status"], [
        ["0. Set-up", "Project folder, private .venv, requirements, run.bat, logging", "Done 29-10-2026"],
        ["1. Shell", "Approved design made real; Rotate PDF and new categories added; dropdown fix",
         "Done 29-10-2026"],
        ["2. Shared engine", "File handling, passwords, page ranges, job queue and worker processes",
         "Done 29-10-2026"],
        ["3. Section 1", "Utilities ported from the earlier tool + Rotate PDF", "Done 29-10-2026"],
        ["4. Section 2", "PDF Converter Pro engine (copied), incl. bank-statement mode", "Done 29-10-2026"],
        ["5. Section 3", "Redaction workspace, OCR redaction, new categories, verification", "Done 29-10-2026"],
        ["6. Finalising and EXE", "User testing and refinements; single-file EXE with Tesseract built in",
         "EXE built 31-10-2026; user testing continuing"],
    ], [3.0, 10.0, 3.5])
    doc.add_heading("Stage 0 and 1 - what was done", 2)
    bullets(doc, [
        "Created E:\\PDF Play Station 2.0 with app\\, assets\\, docs\\, tests\\ and tools\\.",
        "Private Python environment (.venv) with all components installed and verified by "
        "tools\\check_requirements.py; run.bat reinstalls only if requirements.txt changes.",
        "Copied the approved design preview into the new project (the preview itself was not changed) and "
        "converted it from 'design preview' to the application shell (version 2.0.0, own settings store).",
        "Added Rotate PDF with dependent options (page list only for Selected pages; direction disabled "
        "for automatic detection) and a rotate icon.",
        "Extended Smart Redaction to 13 categories and added OCR and OCR-language options to Find & Redact "
        "and Smart Redaction.",
        "Fixed the dropdown highlight and added a visible dropdown arrow; checked on screen: highlight "
        "#EADFCC with navy text.",
    ])
    doc.add_heading("Stage 2 and 3 - what was done", 2)
    bullets(doc, [
        "Shared engine (app/services/common.py, app/jobs.py, app/runners.py) as described in section 3.",
        "All twelve Section 1 tools connected: the earlier tool's engines were ported to the new structure "
        "(same proven logic), and Rotate PDF was built new.",
        "Tool pages now run for real: password prompts, progress with Cancel, result panel with Open folder, "
        "confirmation before sideways pages are turned, Up/Down/Sort for Merge and Images to PDF, and the "
        "Rearrange Pages thumbnail workspace.",
        "Screens checked by driving the real application: merge, sideways detection in the worker process "
        "with confirmation, rearrange with rotate/remove/reverse, and a clear error for an out-of-range page.",
        "Display fixes found during the check: page thumbnails got an outline (white pages on a white grid), "
        "and long folder paths are shortened to drive + last folders (full path in the tooltip).",
    ])

    doc.add_heading("Stage 4 - what was done", 2)
    bullets(doc, [
        "Copied the 15 engine modules of PDF Converter Pro into app/convert (screens, dialogs and the "
        "configuration files were not needed; PDF Converter Pro itself was not changed).",
        "Connected PDF to Excel, PDF to Word, PDF to Excel & Word and Bank Statement to Excel through "
        "app/runners.py: on-screen options are mapped to the engine's settings; results go next to each "
        "PDF unless a folder is chosen; existing files are never overwritten; all four run in the worker "
        "process with progress and Cancel.",
        "Carried over Converter Pro's 98 tests (tests/convert) and added 7 tests for the new connection.",
        "Re-measured the two hand-verified bank statements with the copied engine - identical results.",
        "Found and fixed during the screen check: the engine reported each statement warning twice; the "
        "result panel now shows each warning once.",
    ])

    doc.add_heading("Stage 5 - what was done", 2)
    bullets(doc, [
        "Ported the earlier tool's detection, redaction and verification engine into "
        "app/services/redaction.py (method unchanged) and its workspace to PySide6 (app/redaction_ui.py).",
        "Added the eight new categories with validators (GSTIN check character verified against a "
        "published sample), OCR word positions for scanned pages, OCR re-use within a session, the "
        "black-out check, OCR leak checks after saving and in Verify, and the hand-over to Verify.",
        "Screens checked by driving the real application: Smart detect on a KYC page (PAN, account and "
        "mobile found), a hand-drawn box over the name, Review (4 areas), Apply (all 12 checks PASS), Find "
        "on a scanned page (OCR boxes exactly on the words) and Verify of the redacted file (nothing found).",
    ])

    doc.add_heading("Stage 6 - Windows program (single EXE)", 2)
    para(doc, "Built on 31-10-2026 under a strict packaging brief: analysis and plan first, approval, then "
              "packaging in a separate workspace (E:\\PDF Play Station 2.0 - EXE Build) without touching this "
              "project; the project's file fingerprints were verified unchanged before and after.")
    table(doc, ["Item", "Detail"], [
        ["Deliverable", "PDF Play Station 2.0.exe - one file, about 181 MB, windowed, Windows 10/11 64-bit, no "
                        "administrator rights; version information set; not code-signed; no UPX packing."],
        ["Tool", "PyInstaller 6.22.3 in its own build environment with exactly the application's component "
                 "versions; one-folder build first for testing, then the one-file build."],
        ["Tesseract (option B)", "Bundled: tesseract.exe plus only the 26 DLLs it needs (found by tracing its "
                                 "imports; the training tools are left out) and the eng, hin, mar and osd language "
                                 "data. The application already looked for a bundled 'tesseract' folder, so no "
                                 "code change was needed for this."],
        ["Library data added", "pdfminer CMaps, python-docx template, pypdfium2 files and pdfium.dll; Markdown "
                               "extensions loaded by name declared as hidden imports."],
        ["Code changes (approved; later applied to this project too)",
         "1. multiprocessing.freeze_support() in PDF_Play_Station.py - worker processes start from the EXE. "
         "2. app/logger.py - in the EXE the log goes to %LOCALAPPDATA%\\PDF Play Station 2.0\\logs (the unpack "
         "folder is deleted on exit). 3. app/selftest.py and the hidden --selftest option."],
        ["Self-test (--selftest)", "19 checks on dummy files: environment; all 22 tool pages; bundled Tesseract and "
                                   "its languages; merge, split, rotate (odd and OCR sideways); page numbers and "
                                   "passwords; images; Markdown both ways with Hindi/Marathi; Excel and Word; bank "
                                   "statement (21 rows proven); redaction of a text PDF and of a scanned PDF in a "
                                   "worker process; Hindi/Marathi OCR; worker processes; bad input; a 300-page PDF; "
                                   "a folder without write permission. Options --workdir and --only."],
        ["Results", "One-file EXE: 19/19 on the local disk with Python hidden from PATH and 19/19 on a UNC network "
                    "path; 25 of 25 output files identical to the Python version; window pixel-identical; temporary "
                    "unpack folders removed; start-up 12-20 s (single-file unpacking)."],
        ["Pending", "A clean PC without Python, a NAS/mapped drive and a USB drive, a manual click-through and a "
                    "formal antivirus scan."],
        ["Found during packaging", "Saving into a folder without write permission shows the PDF engine's "
                                   "technical 'Permission denied' message (nothing is written) - existing "
                                   "behaviour, left unchanged; candidate for a later plain-English message."],
    ], [4.0, 12.5])

    doc.add_heading("Refinements from user testing", 2)
    table(doc, ["Date", "Reported", "Change"], [
        ["31-10-2026", "PDF to Excel: the right side of the Options panel was cut off (dropdown arrows, "
                       "Browse button) because of the long label 'Combine all PDFs into one workbook (one "
                       "sheet per PDF)'.",
         "Label shortened to 'One workbook for all PDFs' (full explanation on hover). Tick-box labels now "
         "wrap onto a second line and dropdowns no longer widen the panel, so no label can cut it off "
         "again. Checked on all 17 tool pages: every Options panel fits."],
    ], [2.3, 6.5, 7.7])

    doc.add_heading("Automated tests", 2)
    para(doc, "Run: .venv\\Scripts\\python.exe -m pytest tests   -   188 tests, all passing on 29-10-2026 "
              "(56 for Section 1 and the shared engine, 105 for Section 2, 27 for Section 3). All test "
              "documents are generated on the fly with dummy data.")
    table(doc, ["Test file", "What is proved"], [
        ["test_common.py", "Page lists (1, 3-5, 8-end; descending; en dash), rejection of 0 / out-of-range / "
                           "malformed entries, output names never overwrite ('a (2).pdf'), unsafe characters "
                           "in names replaced."],
        ["test_utilities.py", "Merge order and bookmarks; split; extract order; rearrange with rotation and "
                              "removal; page numbers in all six positions and upright on rotated pages; rotate "
                              "all/odd/even/selected/anticlockwise and adding to existing rotation; content "
                              "untouched by rotation; sideways detection on text pages (5 orientations) and on "
                              "scanned pages via Tesseract; PDF to PNG/JPEG; EXIF photo and multi-page TIFF to "
                              "PDF; protect with and without restrictions; remove password with open vs owner "
                              "password; wrong passwords rejected."],
        ["test_markdown.py", "Markdown to PDF (title, header, table, page number; script removed; missing and "
                             "remote images reported); Hindi and Marathi text; PDF to Markdown headings, lists, "
                             "tables, bold; OCR of a scanned page (and nothing when OCR is off)."],
        ["test_runners.py", "Every connected tool has a runner; batch naming and failure isolation; split "
                            "modes; merge needs two files and never overwrites; rotate modes incl. the "
                            "two-step sideways plan (nothing saved before approval); password confirmation; "
                            "cancel and error reporting; all engines run with network access blocked."],
        ["test_redaction.py", "Each of the 13 categories; Aadhaar and GSTIN check digits; look-alikes not "
                              "flagged (invoice numbers, ordinary dates) or only Low; Find with several terms "
                              "and flexible spacing; engine self-test; scan-apply-verify on a text PDF "
                              "(values gone, neighbouring text unmoved, metadata cleared, original "
                              "untouched); rotated page; annotations and links removed; verification fails "
                              "on an unredacted file; password-protected source; full flattening; Verify "
                              "tool; scanned PDF: detect with OCR, redact, verify, and an independent OCR "
                              "read proving the values are gone while the rest stays readable."],
        ["tests/convert (from Converter Pro)", "Page types; tables (ruled, borderless, multi-page, 20+ "
                                               "columns); Excel cell typing (Indian numbers, dates, text "
                                               "identifiers); Word output incl. wide tables; OCR pipeline; "
                                               "bank statements (amount parsing, reconciliation, dates, "
                                               "totals, harsh synthetic scans); atomic saving and conflicts; "
                                               "cancellation; validators."],
        ["tests/convert/test_section2_runners.py", "Excel next to the source and never overwritten; Word and "
                                                   "both; combined workbook with one damaged PDF; passwords "
                                                   "and page ranges; the bank self-test statement (21 rows, "
                                                   "all proven, Statement and Review sheets, no repeated "
                                                   "warnings); OCR on a scanned PDF; cancel leaves no file."],
    ], [3.5, 13.0])

    # ---- 9 how to run
    doc.add_heading("9. How to run", 1)
    bullets(doc, [
        "Double-click run.bat. First run: creates .venv and installs components (internet needed once). "
        "Later runs start straight away, fully offline.",
        "Tesseract OCR must be installed at C:\\Program Files\\Tesseract-OCR with eng, hin, mar and osd "
        "language data (already installed on this computer).",
        "Logs: logs\\pdf_play_station.log.",
        "Self-test: .venv\\Scripts\\python.exe PDF_Play_Station.py --selftest (result in selftest_report.txt; "
        "the EXE writes its log to %LOCALAPPDATA%\\PDF Play Station 2.0\\logs).",
        "Rebuild this document: .venv\\Scripts\\python.exe docs\\build_dev_document.py",
    ], style="List Number")

    doc.save(OUT)
    return OUT


if __name__ == "__main__":
    print(build())
