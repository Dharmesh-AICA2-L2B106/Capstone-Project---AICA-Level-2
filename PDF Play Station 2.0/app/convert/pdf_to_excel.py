"""Excel workbook generation (openpyxl)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from . import APP_NAME, APP_VERSION
from .cell_values import parse_cell
from .models import DocumentContent, TableData, TextBlock
from .settings import ConversionSettings
from .table_extractor import combine_tables, page_position_flags
from .validators import safe_sheet_name

log = logging.getLogger(__name__)

NAVY = "0B1E3D"
HEADER_FILL = PatternFill("solid", fgColor="EEF1F6")
NOTE_FONT = Font(italic=True, color="5A6475", size=9)
HEADER_FONT = Font(bold=True, color=NAVY)
TITLE_FONT = Font(bold=True, size=13, color=NAVY)
THIN_BOTTOM = Border(bottom=Side(style="thin", color="9AA5B8"))
WRAP_TOP = Alignment(wrap_text=True, vertical="top")
VERIFY_NOTICE = ("Please verify the extracted figures, tables, dates and other critical information "
                 "against the original PDF before relying on this output.")
MAX_COL_WIDTH = 60


class _Writer:
    def __init__(self, settings: ConversionSettings):
        self.s = settings
        self.replaced_chars = 0
        self.sheet_names: set[str] = set()

    # -------------------------------------------------------- cells

    def put(self, ws: Worksheet, row: int, col: int, text: Optional[str], typed: bool = True):
        cell = ws.cell(row=row, column=col)
        if text is None or text == "":
            return cell
        if isinstance(text, str) and ILLEGAL_CHARACTERS_RE.search(text):
            # Control characters cannot be stored in .xlsx. They are shown as
            # U+FFFD (visible replacement mark) and reported, never guessed.
            self.replaced_chars += len(ILLEGAL_CHARACTERS_RE.findall(text))
            text = ILLEGAL_CHARACTERS_RE.sub("�", text)
        if typed:
            parsed = parse_cell(text, self.s.convert_dates, self.s.indian_number_format)
            cell.value = parsed.value
            if parsed.number_format:
                cell.number_format = parsed.number_format
            elif isinstance(parsed.value, str):
                cell.data_type = "s"        # never let "=..." become a formula
                if parsed.value[:1].isdigit() or parsed.value[:1] in "+-":
                    cell.number_format = "@"
        else:
            cell.value = text
            cell.data_type = "s"
        if isinstance(cell.value, str) and "\n" in cell.value:
            cell.alignment = WRAP_TOP
        return cell

    @staticmethod
    def autosize(ws: Worksheet, min_width: int = 8) -> None:
        widths: dict[int, int] = {}
        for row in ws.iter_rows():
            for cell in row:
                if cell.value is None:
                    continue
                text = cell.value if isinstance(cell.value, str) else str(cell.value)
                longest = max((len(part) for part in text.split("\n")), default=0)
                if not isinstance(cell.value, str):
                    longest += 3               # room for thousands separators
                widths[cell.column] = max(widths.get(cell.column, 0), longest)
        for col, width in widths.items():
            ws.column_dimensions[get_column_letter(col)].width = max(min_width, min(width + 2, MAX_COL_WIDTH))
        for row in ws.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and len(cell.value) > MAX_COL_WIDTH and cell.alignment != WRAP_TOP:
                    cell.alignment = WRAP_TOP

    # -------------------------------------------------------- tables

    def write_table(self, ws: Worksheet, table: TableData, start_row: int, structured: bool) -> int:
        """Write a table starting at ``start_row``; returns the next free row."""
        refs = self.s.include_page_refs
        offset = 1 if refs else 0
        row_no = start_row
        header_row: Optional[int] = None
        if table.header_rows:
            header_row = row_no
            if refs:
                self.put(ws, row_no, 1, "Source Page", typed=False)
            for ci, value in enumerate(table.rows[0], start=1 + offset):
                self.put(ws, row_no, ci, value, typed=False)
            for ci in range(1, table.n_cols + offset + 1):
                c = ws.cell(row=row_no, column=ci)
                c.font, c.fill, c.border = HEADER_FONT, HEADER_FILL, THIN_BOTTOM
                c.alignment = Alignment(wrap_text=True, vertical="center")
            row_no += 1
        body = table.rows[table.header_rows:]
        body_pages = (table.row_pages or [table.pages[0]] * len(table.rows))[table.header_rows:]
        for r, values in enumerate(body):
            if refs:
                ws.cell(row=row_no, column=1, value=body_pages[r] if r < len(body_pages) else table.pages[0])
            for ci, value in enumerate(values, start=1 + offset):
                self.put(ws, row_no, ci, value)
            row_no += 1
        if structured and header_row is not None:
            ws.freeze_panes = ws.cell(row=header_row + 1, column=1)
            if row_no - 1 > header_row:
                last = get_column_letter(table.n_cols + offset)
                ws.auto_filter.ref = f"A{header_row}:{last}{row_no - 1}"
        return row_no

    def caption(self, ws: Worksheet, row: int, text: str) -> int:
        self.put(ws, row, 1, text, typed=False)
        ws.cell(row=row, column=1).font = Font(bold=True, color=NAVY)
        return row + 1

    # -------------------------------------------------------- text

    @staticmethod
    def text_rows(doc: DocumentContent) -> list[tuple[int, str, str, str]]:
        """(page, type, text, source) for every non-table text block."""
        rows = []
        for page in doc.pages:
            source = "OCR" if page.method == "ocr" else "Text"
            for item in page.items:
                if isinstance(item, TextBlock) and item.text.strip():
                    kind = {"heading": "Heading", "list_item": "List item"}.get(item.kind, "Paragraph")
                    rows.append((page.number, kind, item.text.replace("\t", "    ").strip(), source))
        return rows

    def write_text_sheet(self, ws: Worksheet, doc: DocumentContent, start_row: int = 1, structured: bool = True) -> int:
        headers = ["Page Number", "Block", "Type", "Extracted Text", "Source"]
        for ci, h in enumerate(headers, start=1):
            c = self.put(ws, start_row, ci, h, typed=False)
            c.font, c.fill, c.border = HEADER_FONT, HEADER_FILL, THIN_BOTTOM
        row = start_row + 1
        block_no: dict[int, int] = {}
        for page, kind, text, source in self.text_rows(doc):
            block_no[page] = block_no.get(page, 0) + 1
            ws.cell(row=row, column=1, value=page)
            ws.cell(row=row, column=2, value=block_no[page])
            self.put(ws, row, 3, kind, typed=False)
            self.put(ws, row, 4, text, typed=False).alignment = WRAP_TOP
            self.put(ws, row, 5, source, typed=False)
            row += 1
        if structured:
            ws.freeze_panes = "A2"
            if row > start_row + 1:
                ws.auto_filter.ref = f"A{start_row}:E{row - 1}"
        return row

    # -------------------------------------------------------- notes

    def write_notes(self, ws: Worksheet, docs: list[DocumentContent]) -> None:
        ws.cell(row=1, column=1, value=f"{APP_NAME} - Conversion notes").font = TITLE_FONT
        self.put(ws, 2, 1, VERIFY_NOTICE, typed=False).font = NOTE_FONT
        row = 4
        headers = ["Source File", "Page", "Page Type", "Extraction Method", "Tables", "Text Blocks",
                   "OCR Confidence %", "Notes"]
        for ci, h in enumerate(headers, start=1):
            c = self.put(ws, row, ci, h, typed=False)
            c.font, c.fill, c.border = HEADER_FONT, HEADER_FILL, THIN_BOTTOM
        row += 1
        method_label = {"text": "Direct text extraction", "ocr": "OCR (verify)", "none": "Not extracted"}
        for doc in docs:
            for page in doc.pages:
                self.put(ws, row, 1, doc.source.name, typed=False)
                ws.cell(row=row, column=2, value=page.number)
                self.put(ws, row, 3, page.kind.capitalize(), typed=False)
                self.put(ws, row, 4, method_label.get(page.method, page.method), typed=False)
                ws.cell(row=row, column=5, value=len(page.tables))
                ws.cell(row=row, column=6, value=len(page.blocks))
                if page.ocr_confidence is not None:
                    ws.cell(row=row, column=7, value=page.ocr_confidence)
                if page.warnings:
                    self.put(ws, row, 8, "\n".join(page.warnings), typed=False).alignment = WRAP_TOP
                row += 1
        if self.replaced_chars:
            row += 1
            self.put(ws, row, 1, f"{self.replaced_chars} control character(s) that Excel cannot store were "
                                 "shown as �.", typed=False).font = NOTE_FONT
        row += 1
        self.put(ws, row, 1, f"Generated by {APP_NAME} {APP_VERSION}. Processed locally on this computer.",
                 typed=False).font = NOTE_FONT
        ws.freeze_panes = "A5"
        self.autosize(ws)
        ws.column_dimensions["H"].width = MAX_COL_WIDTH

    # -------------------------------------------------------- sheets

    def new_sheet(self, wb: Workbook, name: str, fallback: str) -> Worksheet:
        return wb.create_sheet(safe_sheet_name(name, self.sheet_names, fallback))

    def tables_for(self, doc: DocumentContent) -> list[TableData]:
        per_page = [p.tables for p in doc.pages]
        flat, first, last = page_position_flags(per_page)
        if self.s.sheet_mode == "combine":
            return combine_tables(flat, first, last)
        return flat

    def write_document_sheets(self, wb: Workbook, doc: DocumentContent) -> None:
        """Workbook-per-PDF layout."""
        if self.s.sheet_mode == "per_page":
            for page in doc.pages:
                if not page.tables and not (self.s.include_text_sheet and page.blocks):
                    continue
                ws = self.new_sheet(wb, f"Page_{page.number:03d}", "Page")
                row = 1
                single = len(page.tables) == 1 and not (self.s.include_text_sheet and page.blocks)
                for ti, table in enumerate(page.tables, start=1):
                    if not single:
                        row = self.caption(ws, row, f"Table {ti} (page {page.number})")
                    row = self.write_table(ws, table, row, structured=single) + 1
                if self.s.include_text_sheet and page.blocks:
                    sub = DocumentContent(doc.source, doc.page_count, [page])
                    row = self.caption(ws, row, f"Text (page {page.number})")
                    self.write_text_sheet(ws, sub, row, structured=False)
                self.autosize(ws)
        else:
            for ti, table in enumerate(self.tables_for(doc), start=1):
                ws = self.new_sheet(wb, f"Table_{ti:03d}", "Table")
                self.write_table(ws, table, 1, structured=True)
                self.autosize(ws)
            if self.s.include_text_sheet and self.text_rows(doc):
                ws = self.new_sheet(wb, "Extracted_Text", "Text")
                self.write_text_sheet(ws, doc)
                self.autosize(ws)
                ws.column_dimensions["D"].width = 100

    def write_combined_sheet(self, wb: Workbook, doc: DocumentContent, index: int) -> None:
        """Combined-workbook layout: one sheet per source PDF."""
        stem = doc.source.stem
        ws = self.new_sheet(wb, stem if stem else f"Document_{index:03d}", f"Document_{index:03d}")
        self.put(ws, 1, 1, f"Source: {doc.source.name}", typed=False).font = TITLE_FONT
        row = 3
        for ti, table in enumerate(self.tables_for(doc), start=1):
            pages = ", ".join(str(p) for p in table.pages)
            row = self.caption(ws, row, f"Table {ti} (page {pages})")
            row = self.write_table(ws, table, row, structured=False) + 1
        if self.s.include_text_sheet and self.text_rows(doc):
            row = self.caption(ws, row, "Extracted text")
            self.write_text_sheet(ws, doc, row, structured=False)
        self.autosize(ws)


def build_workbook(docs: list[DocumentContent], settings: ConversionSettings) -> tuple[Workbook, list[str]]:
    """Create the workbook in memory. Returns (workbook, warnings)."""
    writer = _Writer(settings)
    wb = Workbook()
    wb.remove(wb.active)
    warnings: list[str] = []
    combined = len(docs) > 1 or settings.workbook_mode == "combined"
    for i, doc in enumerate(docs, start=1):
        if combined:
            writer.write_combined_sheet(wb, doc, i)
        else:
            writer.write_document_sheets(wb, doc)
        if not doc.tables:
            warnings.append(f"{doc.source.name}: no tables were detected"
                            + ("; the text was exported instead." if settings.include_text_sheet and writer.text_rows(doc) else "."))
    notes = wb.create_sheet(safe_sheet_name("Conversion_Notes", writer.sheet_names, "Notes"))
    writer.write_notes(notes, docs)
    if writer.replaced_chars:
        warnings.append(f"{writer.replaced_chars} unprintable control character(s) were shown as � in Excel.")
    wb.active = 0
    wb.properties.creator = APP_NAME
    wb.properties.title = docs[0].source.stem if len(docs) == 1 else "Combined conversion"
    return wb, warnings


def write_excel(docs: list[DocumentContent], target: Path, settings: ConversionSettings) -> list[str]:
    wb, warnings = build_workbook(docs, settings)
    wb.save(str(target))
    return warnings
