"""Plain data structures shared by the extraction and output modules.

Coordinates are PDF points measured from the top-left corner of the page
(the pdfplumber convention). OCR results are converted to the same units so
that one layout pipeline serves both text-based and scanned pages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union


@dataclass
class Word:
    text: str
    x0: float
    x1: float
    top: float
    bottom: float
    size: float = 10.0
    fontname: str = ""
    bold: bool = False
    italic: bool = False
    link: Optional[str] = None
    conf: Optional[float] = None   # OCR confidence 0-100; None for native text

    @property
    def height(self) -> float:
        return max(self.bottom - self.top, 0.1)

    @property
    def xc(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def yc(self) -> float:
        return (self.top + self.bottom) / 2


@dataclass
class Run:
    text: str
    bold: bool = False
    italic: bool = False
    size: Optional[float] = None
    font: Optional[str] = None
    link: Optional[str] = None


@dataclass
class TextBlock:
    kind: str                      # heading | paragraph | list_item
    runs: list[Run]
    top: float = 0.0
    level: int = 0                 # heading level 1-3
    align: str = "left"            # left | center | right
    indent: float = 0.0            # left indent in points (relative to text column)
    first_line_indent: float = 0.0

    @property
    def text(self) -> str:
        return "".join(r.text for r in self.runs)


@dataclass
class TableData:
    rows: list[list[Optional[str]]]
    pages: list[int]                        # source page numbers (1-based)
    row_pages: list[int] = field(default_factory=list)
    top: float = 0.0
    bbox: Optional[tuple[float, float, float, float]] = None
    header_rows: int = 0
    source: str = "lines"                   # lines | text | ocr
    continued_from_previous: bool = False

    @property
    def n_cols(self) -> int:
        return max((len(r) for r in self.rows), default=0)

    @property
    def header(self) -> list[Optional[str]]:
        return self.rows[0] if self.header_rows and self.rows else []


PageItem = Union[TextBlock, TableData]


@dataclass
class PageContent:
    number: int                              # 1-based page number in the source PDF
    width: float
    height: float
    kind: str = "text"                       # text | scanned | mixed | blank
    method: str = "text"                     # text | ocr | none
    items: list[PageItem] = field(default_factory=list)
    image_path: Optional[Path] = None        # rendered page image when needed
    ocr_confidence: Optional[float] = None
    warnings: list[str] = field(default_factory=list)
    margins: tuple[float, float, float, float] = (72.0, 72.0, 72.0, 72.0)  # l, t, r, b

    @property
    def tables(self) -> list[TableData]:
        return [i for i in self.items if isinstance(i, TableData)]

    @property
    def blocks(self) -> list[TextBlock]:
        return [i for i in self.items if isinstance(i, TextBlock)]

    @property
    def has_content(self) -> bool:
        return any(isinstance(i, TableData) or i.text.strip() for i in self.items)


@dataclass
class DocumentContent:
    source: Path
    page_count: int
    pages: list[PageContent] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ocr_pages(self) -> list[int]:
        return [p.number for p in self.pages if p.method == "ocr"]

    @property
    def tables(self) -> list[TableData]:
        return [t for p in self.pages for t in p.tables]


@dataclass
class FileResult:
    source: Path
    status: str = "pending"        # success | warning | failed | skipped | cancelled
    outputs: list[Path] = field(default_factory=list)
    pages_processed: int = 0
    ocr_pages: int = 0
    tables_found: int = 0
    statement_rows: int = 0          # bank-statement mode: transactions extracted
    statement_flags: int = 0         # bank-statement mode: rows marked Inferred / Check
    warnings: list[str] = field(default_factory=list)
    error: str = ""

    @property
    def needed_ocr(self) -> bool:
        return self.ocr_pages > 0


@dataclass
class BatchSummary:
    results: list[FileResult] = field(default_factory=list)
    output_folder: Optional[Path] = None
    cancelled: bool = False
    combined_output: Optional[Path] = None

    def count(self, *statuses: str) -> int:
        return sum(1 for r in self.results if r.status in statuses)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def succeeded(self) -> int:
        return self.count("success", "warning")

    @property
    def failed(self) -> int:
        return self.count("failed")

    @property
    def skipped(self) -> int:
        return self.count("skipped", "cancelled")

    @property
    def pages(self) -> int:
        return sum(r.pages_processed for r in self.results)

    @property
    def files_with_ocr(self) -> int:
        return sum(1 for r in self.results if r.needed_ocr)
