"""Word document generation (python-docx).

Modes
-----
editable  Paragraphs, headings, lists, tables, fonts, alignment and page size
          reconstructed as editable Word content (default).
layout    Each page is placed as a full-page picture for visual similarity,
          followed by an editable-text appendix. The pictures are not editable.
text      Clean text and tables only; page geometry and fonts are not copied.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from docx import Document
from docx.enum.section import WD_ORIENT, WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.opc.constants import RELATIONSHIP_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Emu, Pt, RGBColor

from . import APP_NAME
from .models import DocumentContent, PageContent, Run, TableData, TextBlock
from .settings import ConversionSettings

log = logging.getLogger(__name__)

NOTE_COLOR = RGBColor(0x5A, 0x64, 0x75)
OCR_COLOR = RGBColor(0x8A, 0x6A, 0x3E)
LINK_COLOR = RGBColor(0x1E, 0x4E, 0x8C)
ALIGN = {"left": WD_ALIGN_PARAGRAPH.LEFT, "center": WD_ALIGN_PARAGRAPH.CENTER, "right": WD_ALIGN_PARAGRAPH.RIGHT}
MIN_MARGIN, MAX_MARGIN = 18.0, 108.0   # points
_XML_BAD = {c for c in range(32) if c not in (9, 10, 13)}


def _xml_safe(text: str) -> str:
    """Word XML cannot hold control characters; show them as U+FFFD."""
    return "".join("�" if ord(ch) in _XML_BAD else ch for ch in text)


class _WordWriter:
    def __init__(self, settings: ConversionSettings):
        self.s = settings
        self.doc = Document()
        self.first_page = True
        self.pending_break = False
        normal = self.doc.styles["Normal"]
        normal.font.name = "Calibri"
        normal.font.size = Pt(11)
        normal.paragraph_format.space_after = Pt(4)

    # -------------------------------------------------------- page setup

    def start_page(self, page: PageContent, margins: Optional[tuple[float, float, float, float]]) -> None:
        width, height = Pt(page.width), Pt(page.height)
        if self.first_page:
            section = self.doc.sections[0]
        else:
            current = self.doc.sections[-1]
            same_size = abs(current.page_width - width) < Pt(2) and abs(current.page_height - height) < Pt(2)
            if self.s.word_mode != "text" and not same_size:
                section = self.doc.add_section(WD_SECTION.NEW_PAGE)
                self.pending_break = False
            else:
                section = None
                self.pending_break = self.s.preserve_page_breaks
        if section is not None and self.s.word_mode != "text":
            section.page_width, section.page_height = width, height
            section.orientation = WD_ORIENT.LANDSCAPE if page.width > page.height else WD_ORIENT.PORTRAIT
            if margins:
                l, t, r, b = (min(max(m, MIN_MARGIN), MAX_MARGIN) for m in margins)
                section.left_margin, section.top_margin = Pt(l), Pt(t)
                section.right_margin, section.bottom_margin = Pt(r), Pt(b)
        self.first_page = False

    def paragraph(self, style: Optional[str] = None):
        p = self.doc.add_paragraph(style=style)
        if self.pending_break:
            p.paragraph_format.page_break_before = True
            self.pending_break = False
        return p

    def flush_break_for_table(self) -> None:
        if self.pending_break:
            p = self.doc.add_paragraph()
            p.add_run().add_break(WD_BREAK.PAGE)
            self.pending_break = False

    def usable_width(self) -> int:
        s = self.doc.sections[-1]
        return int(s.page_width - s.left_margin - s.right_margin)

    def usable_height(self) -> int:
        s = self.doc.sections[-1]
        return int(s.page_height - s.top_margin - s.bottom_margin)

    # -------------------------------------------------------- content

    def note(self, text: str, color: RGBColor = NOTE_COLOR) -> None:
        p = self.paragraph()
        run = p.add_run(text)
        run.italic = True
        run.font.size = Pt(8)
        run.font.color.rgb = color

    def add_runs(self, p, runs: list[Run], keep_fonts: bool) -> None:
        for r in runs:
            if not r.text:
                continue
            text = _xml_safe(r.text)
            if r.link and r.link.lower().startswith(("http://", "https://", "mailto:")):
                self._hyperlink(p, text, r.link, r, keep_fonts)
                continue
            run = p.add_run(text)
            self._style_run(run, r, keep_fonts)

    def _style_run(self, run, r: Run, keep_fonts: bool) -> None:
        run.bold = r.bold or None
        run.italic = r.italic or None
        if keep_fonts:
            if r.size:
                run.font.size = Pt(min(max(r.size, 6.0), 48.0))
            if r.font:
                run.font.name = r.font

    def _hyperlink(self, p, text: str, url: str, r: Run, keep_fonts: bool) -> None:
        part = p.part
        rel_id = part.relate_to(url, RELATIONSHIP_TYPE.HYPERLINK, is_external=True)
        link = OxmlElement("w:hyperlink")
        link.set(qn("r:id"), rel_id)
        run = p.add_run(text)
        self._style_run(run, r, keep_fonts)
        run.font.color.rgb = LINK_COLOR
        run.underline = True
        link.append(run._r)
        p._p.append(link)

    def block(self, block: TextBlock) -> None:
        editable = self.s.word_mode != "text"
        if block.kind == "heading":
            p = self.paragraph(f"Heading {min(max(block.level, 1), 3)}")
            self.add_runs(p, [Run(r.text, r.bold, r.italic, None, None, r.link) for r in block.runs], False)
        else:
            p = self.paragraph()
            self.add_runs(p, block.runs, keep_fonts=editable)
        if editable:
            p.alignment = ALIGN.get(block.align, WD_ALIGN_PARAGRAPH.LEFT)
            if block.indent > 1:
                p.paragraph_format.left_indent = Pt(min(block.indent, 300))
            if abs(block.first_line_indent) > 1:
                p.paragraph_format.first_line_indent = Pt(max(min(block.first_line_indent, 200), -200))

    def table(self, table: TableData, ocr: bool) -> None:
        self.flush_break_for_table()
        n_cols = table.n_cols
        if n_cols == 0:
            return
        if ocr or table.source != "lines":
            how = "OCR" if ocr else "column alignment"
            self.note(f"Table reconstructed from {how} (page {', '.join(map(str, table.pages))}) - verify cell boundaries.",
                      OCR_COLOR if ocr else NOTE_COLOR)
        # Smaller cell text for wide tables so 10-25 columns fit across the page.
        cell_pt = 9 if n_cols <= 8 else 8 if n_cols <= 12 else 7 if n_cols <= 18 else 6
        t = self.doc.add_table(rows=len(table.rows), cols=n_cols)
        t.style = "Table Grid"
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        for ri, row in enumerate(table.rows):
            cells = t.rows[ri].cells
            for ci in range(n_cols):
                value = row[ci] if ci < len(row) else None
                if not value:
                    continue
                para = cells[ci].paragraphs[0]
                para.paragraph_format.space_after = Pt(0)
                for li, line in enumerate(_xml_safe(value).split("\n")):
                    if li:
                        para.add_run().add_break()
                    run = para.add_run(line)
                    run.font.size = Pt(cell_pt)
                    if ri < table.header_rows:
                        run.bold = True
            if ri < table.header_rows:
                tr_pr = t.rows[ri]._tr.get_or_add_trPr()
                header = OxmlElement("w:tblHeader")
                header.set(qn("w:val"), "true")
                tr_pr.append(header)
        self.doc.add_paragraph().paragraph_format.space_after = Pt(2)

    def picture(self, path: Path) -> None:
        """Insert a page image scaled to fit the usable page area."""
        from PIL import Image
        with Image.open(path) as im:
            w_px, h_px = im.size
        max_w, max_h = self.usable_width(), self.usable_height() - int(Pt(12))
        ratio = min(max_w / w_px, max_h / h_px)
        p = self.paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(0)
        p.add_run().add_picture(str(path), width=Emu(int(w_px * ratio)), height=Emu(int(h_px * ratio)))

    # -------------------------------------------------------- pages

    def page_content(self, page: PageContent, label_pages: bool, pictures: bool = True) -> None:
        ocr = page.method == "ocr"
        if label_pages:
            if self.s.word_mode == "text":
                self.paragraph("Heading 2").add_run(f"Page {page.number}")
            else:
                self.note(f"Source page {page.number}")
        if ocr:
            conf = f" (average confidence {page.ocr_confidence:.0f}%)" if page.ocr_confidence is not None else ""
            self.note(f"Page {page.number}: text recognised by OCR{conf}. Verify against the original PDF.", OCR_COLOR)
        if page.method == "none":
            msg = "; ".join(page.warnings) or f"Page {page.number}: no text could be extracted."
            self.note(msg, OCR_COLOR)
        if pictures and page.image_path and (page.method == "none" or (ocr and self.s.preserve_scanned_images)):
            self.picture(page.image_path)
        for item in page.items:
            if isinstance(item, TableData):
                self.table(item, ocr)
            elif isinstance(item, TextBlock) and item.text.strip():
                self.block(item)

    def build(self, content: DocumentContent) -> None:
        mode = self.s.word_mode
        if mode == "layout":
            for page in content.pages:
                self.start_page(page, (14.0, 14.0, 14.0, 14.0))
                if page.image_path:
                    self.picture(page.image_path)
                else:
                    self.note(f"Page {page.number}: the page image could not be rendered.")
            self.doc.add_section(WD_SECTION.NEW_PAGE)
            p = self.doc.add_paragraph(style="Heading 1")
            p.add_run("Editable text (extracted)")
            self.note("The pages above are pictures of the original pages and are not editable. "
                      "The editable text and tables extracted from each page follow.")
            for page in content.pages:
                self.page_content(page, label_pages=True, pictures=False)
        else:
            for page in content.pages:
                margins = page.margins if mode == "editable" else None
                self.start_page(page, margins)
                self.page_content(page, label_pages=self.s.include_page_refs)
        props = self.doc.core_properties
        props.author = APP_NAME
        props.title = content.source.stem
        props.comments = "Converted from PDF. Verify critical information against the original."


def write_word(content: DocumentContent, target: Path, settings: ConversionSettings) -> list[str]:
    writer = _WordWriter(settings)
    writer.build(content)
    writer.doc.save(str(target))
    warnings: list[str] = []
    if settings.word_mode == "layout":
        warnings.append(f"{content.source.name}: layout-preserving mode uses page pictures; "
                        "use the editable-text appendix for editing.")
    return warnings
