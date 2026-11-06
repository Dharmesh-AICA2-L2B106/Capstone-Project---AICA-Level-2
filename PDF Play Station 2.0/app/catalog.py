"""The tool catalogue: three sections, every tool, its description and its options.

This is the single place that defines what appears in the sidebar and on each
tool page. When a tool's processing is connected later, it gets a `runner`
here; the UI does not need to change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from . import theme


@dataclass
class Option:
    kind: str                       # combo | text | lines | password | check | checks | spin | pages | info
    label: str
    choices: list[str] = field(default_factory=list)
    default: object = None
    tip: str = ""
    placeholder: str = ""
    # (label of a combo option, choices) - this option is only enabled while that
    # combo shows one of the choices, e.g. page list only for "Selected pages".
    enabled_when: Optional[tuple[str, tuple[str, ...]]] = None


@dataclass
class Tool:
    id: str
    name: str
    icon: str
    summary: str                    # one line, shown on the tool page and in search
    action: str                     # text of the run button
    accepts: str = "pdf"            # pdf | images | markdown
    multi: bool = True              # accepts several files
    workspace: str = ""             # "" = file list; otherwise a visual workspace (pages / redactions)
    options: list[Option] = field(default_factory=list)
    ready: bool = False             # True once its engine is connected (app/runners.py)
    ordered: bool = False           # the order of the files matters (Up / Down / Sort buttons)


@dataclass
class Section:
    id: str
    name: str
    icon: str
    color: str
    blurb: str
    tools: list[Tool]


PAGES = Option("pages", "Pages", placeholder="All pages  (e.g. 1, 3-5, 8-10)", tip="Leave blank for every page")
OCR = Option("combo", "OCR for scanned pages", ["Automatic (recommended)", "Always run OCR", "Off"])
OCR_LANG = Option("combo", "OCR language", ["English", "English + Hindi", "English + Marathi",
                                            "English + Hindi + Marathi"], default="English + Hindi + Marathi")
ROTATE_WHICH = ["All pages", "Selected pages", "Odd pages only", "Even pages only",
                "Sideways pages (detected automatically)"]
# Conversion: English OCR reads figures most reliably; Hindi / Marathi when the text needs it.
OCR_LANG_CONVERT = Option("combo", "OCR language", OCR_LANG.choices, default="English")
WORKSHEETS = Option("combo", "Worksheets", ["Combine continued tables", "One sheet per table", "One sheet per page"])
WORD_MODE = Option("combo", "Word mode", ["Editable document", "Layout-preserving", "Text extraction"])
INDIAN = Option("check", "Indian number format (1,00,000)", default=True)
MD_FONTS = ["Segoe UI", "Calibri", "Arial", "Times New Roman", "Georgia", "Helvetica (built-in)",
            "Times (built-in)"]
SMART_CATEGORIES = ["PAN", "Aadhaar", "GSTIN", "TAN", "CIN", "DIN", "Bank account numbers", "IFSC",
                    "Passport", "Voter ID", "Mobile numbers", "E-mail addresses", "Dates of birth"]

SECTIONS: list[Section] = [
    Section("utilities", "PDF & Document Utilities", "grid", theme.NAVY,
            "Merge, split, number, rearrange, protect and convert PDFs and images.", [
        Tool("merge", "Merge PDF", "merge", "Combine several PDFs into one file, in the order you choose.",
             "Merge PDFs", ready=True, ordered=True, options=[
                 Option("text", "Output file name", default="Merged.pdf"),
                 Option("check", "Add a bookmark for each original file", default=True)]),
        Tool("split", "Split PDF", "split", "Split PDFs into several smaller files.", "Split PDF",
             ready=True, options=[
                 Option("combo", "Split by", ["Every N pages", "Page ranges", "Every page"]),
                 Option("spin", "N (pages per file)", default=1,
                        enabled_when=("Split by", ("Every N pages",))),
                 Option("pages", "Page ranges", placeholder="e.g. 1-3, 4-10  (one file per range)",
                        enabled_when=("Split by", ("Page ranges",)))]),
        Tool("extract", "Extract Pages", "extract", "Copy the pages you choose into a new PDF.", "Extract pages",
             ready=True, options=[Option("pages", "Pages", placeholder="e.g. 1, 3-5, 8-end",
                                         tip="In the order you type them")]),
        Tool("numbering", "Page Numbering", "hash", "Add page numbers to every page.", "Add page numbers",
             ready=True, options=[
                 Option("combo", "Position", ["Bottom centre", "Bottom right", "Bottom left", "Top centre",
                                              "Top right", "Top left"]),
                 Option("combo", "Format", ["1", "Page 1", "Page 1 of N", "1 / N"]),
                 Option("spin", "Start at", default=1),
                 Option("spin", "Font size", default=10), PAGES]),
        Tool("rearrange", "Rearrange Pages", "rearrange", "Drag pages into a new order, rotate or delete them.",
             "Save new order", multi=False, workspace="pages", ready=True),
        Tool("rotate", "Rotate PDF", "rotate", "Turn all, selected, odd or even pages - or fix sideways scans.",
             "Rotate pages", ready=True, options=[
                 Option("combo", "Rotate which pages", ROTATE_WHICH),
                 Option("pages", "Page numbers", placeholder="e.g. 2, 5-7, 10",
                        enabled_when=("Rotate which pages", ("Selected pages",))),
                 Option("combo", "Direction", ["90° clockwise", "90° anticlockwise", "180° (upside down)"],
                        enabled_when=("Rotate which pages", tuple(ROTATE_WHICH[:4]))),
                 Option("info", "", default="Sideways pages are found from the direction of their text (scanned "
                                            "pages: Tesseract's orientation check) and turned upright; you see "
                                            "the list before anything is saved.")]),
        Tool("pdf2img", "PDF to Images", "image", "Save each page as a PNG or JPEG image.", "Create images",
             ready=True, options=[Option("combo", "Format", ["PNG", "JPEG"]),
                                  Option("combo", "Resolution", ["150 dpi", "200 dpi", "300 dpi"],
                                         default="200 dpi"), PAGES]),
        Tool("img2pdf", "Images to PDF", "images-pdf", "Turn photos or scans into one PDF.", "Create PDF",
             accepts="images", ready=True, ordered=True, options=[
                 Option("text", "Output file name", placeholder="Blank = first image's name"),
                 Option("combo", "Page size", ["A4", "Letter", "Fit to image"]),
                 Option("combo", "Orientation", ["Automatic", "Portrait", "Landscape"],
                        enabled_when=("Page size", ("A4", "Letter"))),
                 Option("info", "", default="Phone photos are turned upright automatically; every page of a "
                                            "multi-page TIFF is included.")]),
        Tool("protect", "Password Protect PDF", "lock", "Add an open password and optional restrictions.",
             "Protect PDF", ready=True, options=[
                 Option("password", "Password"), Option("password", "Confirm password"),
                 Option("checks", "Allow", ["Printing", "Copying text", "Editing"],
                        default=["Printing", "Copying text", "Editing"]),
                 Option("password", "Permissions password (optional)",
                        tip="Needed later to lift the restrictions. Must differ from the open password."),
                 Option("info", "", default="AES-256 encryption. The protected file is re-opened with the "
                                            "password to verify it. Passwords are never saved.")]),
        Tool("unprotect", "Remove PDF Password", "unlock",
             "Remove the password from a PDF you are authorised to open.", "Remove password", ready=True, options=[
                 Option("password", "Current password",
                        tip="Leave blank to be asked for each file"),
                 Option("info", "", default="Only for PDFs you are authorised to open. A known password is "
                                            "used - nothing is cracked. Passwords are never saved.")]),
        Tool("md2pdf", "Markdown to PDF", "markdown", "Turn Markdown (.md) notes into a formatted PDF.",
             "Create PDF", accepts="markdown", ready=True, options=[
                 Option("combo", "Page size", ["A4", "Letter"]),
                 Option("combo", "Orientation", ["Portrait", "Landscape"]),
                 Option("combo", "Font", MD_FONTS, default="Segoe UI"),
                 Option("combo", "Font size", ["9", "10", "10.5", "11", "12"], default="10.5"),
                 Option("check", "Page numbers (Page 1 of N)", default=True),
                 Option("text", "Title (optional)"),
                 Option("text", "Header text (optional)"),
                 Option("text", "Footer text (optional)")]),
        Tool("pdf2md", "PDF to Markdown", "markdown", "Extract the text of a PDF as Markdown.", "Create Markdown",
             ready=True, options=[
                 Option("check", "Detect tables", default=True),
                 Option("check", "Save images next to the .md file", default=True),
                 Option("check", "Remove repeated headers / footers", default=True),
                 Option("check", "Mark page breaks", default=False),
                 OCR, OCR_LANG, PAGES]),
    ]),
    Section("convert", "Convert to Excel / Word", "sheet", theme.EXCEL,
            "Editable Excel and Word files, including balance-checked bank statements.", [
        Tool("to_excel", "PDF to Excel", "sheet", "Tables and figures into editable .xlsx workbooks.",
             "Convert to Excel", ready=True, options=[
                 WORKSHEETS,
                 Option("check", "One workbook for all PDFs", default=False,
                        tip="Several PDFs: one Excel file with a sheet per PDF, instead of one file per PDF."),
                 INDIAN, OCR, OCR_LANG_CONVERT, PAGES]),
        Tool("to_word", "PDF to Word", "doc", "Editable .docx documents with headings, lists and tables.",
             "Convert to Word", ready=True, options=[WORD_MODE, OCR, OCR_LANG_CONVERT, PAGES]),
        Tool("to_both", "PDF to Excel & Word", "layers", "Create both an Excel and a Word file for every PDF.",
             "Convert", ready=True, options=[WORKSHEETS, WORD_MODE, INDIAN, OCR, OCR_LANG_CONVERT, PAGES]),
        Tool("bank", "Bank Statement to Excel", "bank",
             "Every row proven against the running balance; anything unproven is flagged for review.",
             "Convert statement", ready=True, options=[
                 OCR, OCR_LANG_CONVERT, PAGES,
                 Option("info", "", default="Each transaction is checked against the running balance. Doubtful "
                                            "figures are re-read at higher resolution; anything still unproven "
                                            "is marked Inferred or Check and listed on the Review sheet. The "
                                            "bank's printed totals are compared on a separate sheet.")]),
    ]),
    Section("redaction", "Secure Redaction", "shield", theme.ERROR,
            "Permanently remove confidential information - and prove it is gone.", [
        # Manual, Find, Smart, Review and Apply share one workspace (app/redaction_ui.py); their
        # options are listed here for the catalogue and the development document.
        Tool("manual", "Manual Redaction", "redact", "Draw boxes over anything you want removed.",
             "Mark for redaction", multi=False, workspace="redact", ready=True, options=[
                 Option("info", "", default="Drag on the page to mark; move, resize, delete; undo.")]),
        Tool("find", "Find & Redact", "find", "Search for words or numbers and mark every occurrence.",
             "Find matches", multi=False, workspace="redact", ready=True, options=[
                 Option("lines", "Search for", placeholder="One term per line"),
                 Option("check", "Match case", default=False),
                 Option("check", "Whole words only", default=True),
                 Option("check", "Ignore spaces / hyphens", default=True), OCR, OCR_LANG]),
        Tool("smart", "Smart Redaction", "sparkles", "Detect personal data automatically (DPDP-sensitive).",
             "Detect personal data", multi=False, workspace="redact", ready=True, options=[
                 Option("checks", "Detect", SMART_CATEGORIES, default=list(SMART_CATEGORIES)),
                 Option("check", "PAN in any letter case", default=False),
                 Option("check", "Bank account: only with 'A/c No.' or similar nearby", default=True),
                 OCR, OCR_LANG]),
        Tool("review", "Review Redactions", "eye", "Check every marked area before anything is removed.",
             "Accept reviewed marks", multi=False, workspace="redact", ready=True, options=[
                 Option("info", "", default="Tick / untick each area; click to see it on the page.")]),
        Tool("apply", "Apply Redactions", "check-square", "Permanently remove the marked content.",
             "Apply redactions", multi=False, workspace="redact", ready=True, options=[
                 Option("combo", "Patch resolution", ["150 dpi", "200 dpi", "300 dpi", "400 dpi"], default="300 dpi"),
                 Option("combo", "Drawings", ["Remove drawings fully inside a region",
                                              "Remove drawings touching a region"]),
                 Option("check", "Also remove metadata, JavaScript, attachments and history", default=True),
                 Option("check", "Flatten redacted pages fully (maximum safety)", default=False),
                 Option("check", "Check scanned pages with OCR after saving", default=True)]),
        Tool("verify", "Verify Redacted PDF", "verify",
             "Prove that redacted text can no longer be found or copied.", "Verify PDF", ready=True, options=[
                 Option("lines", "Values that must not appear", placeholder="One per line - e.g. a PAN, an account "
                                                                            "number or a name"),
                 Option("check", "Read scanned pages with OCR", default=True), OCR_LANG,
                 Option("info", "", default="Checks text, annotations, metadata, bookmarks, JavaScript, embedded "
                                            "files and earlier revisions. Values are shown masked.")]),
    ]),
]

ALL_TOOLS: dict[str, tuple[Section, Tool]] = {t.id: (s, t) for s in SECTIONS for t in s.tools}
POPULAR = ["merge", "split", "rotate", "to_excel", "bank", "smart"]
