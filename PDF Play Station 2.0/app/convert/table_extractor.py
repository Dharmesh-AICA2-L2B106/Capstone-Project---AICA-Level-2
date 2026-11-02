"""Table extraction and multi-page table combination.

Two complementary strategies are used:

* Ruled tables (cell borders drawn as lines) are found with pdfplumber's
  line-intersection algorithm.
* Borderless tables (columns aligned with white space, typical of bank
  statements and ledgers) are found by :func:`layout.detect_text_tables`,
  which also serves OCR output.
"""

from __future__ import annotations

import logging
import re
from dataclasses import replace
from typing import Any, Optional

from .layout import mark_header
from .models import TableData, Word

log = logging.getLogger(__name__)

RULED_SETTINGS: dict[str, Any] = {
    "vertical_strategy": "lines",
    "horizontal_strategy": "lines",
    "snap_tolerance": 3,
    "join_tolerance": 3,
    "intersection_tolerance": 3,
    "edge_min_length": 3,
}

_SPACES = re.compile(r"[ \t ]+")


def _clean_cell(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    lines = [_SPACES.sub(" ", part).strip() for part in str(value).splitlines()]
    text = "\n".join(l for l in lines if l)
    return text or None


def clean_rows(rows: list[list[Optional[str]]]) -> list[list[Optional[str]]]:
    """Normalise whitespace, pad ragged rows and drop rows/columns that are
    completely empty (they carry no data and only come from drawing artefacts).
    Blank cells inside the table are preserved to keep alignment."""
    cleaned = [[_clean_cell(c) for c in row] for row in rows]
    width = max((len(r) for r in cleaned), default=0)
    cleaned = [r + [None] * (width - len(r)) for r in cleaned]
    cleaned = [r for r in cleaned if any(c for c in r)]
    if not cleaned:
        return []
    keep = [ci for ci in range(width) if any(r[ci] for r in cleaned)]
    return [[r[ci] for ci in keep] for r in cleaned]


def extract_ruled_tables(page: Any, page_no: int) -> list[TableData]:
    """Tables with drawn borders on a pdfplumber page."""
    tables: list[TableData] = []
    try:
        found = page.find_tables(RULED_SETTINGS)
    except Exception:  # pdfplumber can fail on unusual drawing operators
        log.warning("Ruled-table detection failed on page %s", page_no, exc_info=True)
        return tables
    for t in found:
        try:
            rows = clean_rows(t.extract())
        except Exception:
            log.warning("Could not read a table on page %s", page_no, exc_info=True)
            continue
        if len(rows) < 2 or max(len(r) for r in rows) < 2:
            continue      # a box around a paragraph, not a table
        table = TableData(rows=rows, pages=[page_no], row_pages=[page_no] * len(rows),
                          top=float(t.bbox[1]), bbox=tuple(float(v) for v in t.bbox), source="lines")
        mark_header(table)
        tables.append(table)
    return tables


def words_outside(words: list[Word], tables: list[TableData], pad: float = 1.0) -> list[Word]:
    boxes = [t.bbox for t in tables if t.bbox]
    if not boxes:
        return words
    return [w for w in words
            if not any(b[0] - pad <= w.xc <= b[2] + pad and b[1] - pad <= w.yc <= b[3] + pad for b in boxes)]


def _norm_row(row: list[Optional[str]]) -> tuple[str, ...]:
    return tuple(re.sub(r"\s+", " ", (c or "")).strip().lower() for c in row)


def combine_tables(tables: list[TableData], first_on_page: set[int], last_on_page: set[int]) -> list[TableData]:
    """Join tables that continue onto the following page.

    ``first_on_page`` / ``last_on_page`` hold indexes (into ``tables``) of tables
    that are the first / last table on their page. A table is treated as a
    continuation when it is the first table on the page directly after the
    previous table's page, is the last one there, has the same number of
    columns, and either repeats the same header or has no header of its own.
    A repeated header row is dropped so it does not appear in the middle of
    the combined data.
    """
    result: list[TableData] = []
    prev_index: Optional[int] = None
    for i, t in enumerate(tables):
        prev = result[-1] if result else None
        joined = False
        if prev is not None and prev_index is not None \
                and prev_index in last_on_page and i in first_on_page \
                and t.pages[0] == prev.pages[-1] + 1 and t.n_cols == prev.n_cols:
            rows, row_pages = t.rows, t.row_pages
            if t.header_rows and prev.header_rows:
                if _norm_row(t.rows[0]) == _norm_row(prev.rows[0]):
                    rows, row_pages = rows[1:], row_pages[1:]
                    joined = True
            elif not t.header_rows:
                joined = True
            if joined:
                prev.rows.extend([list(r) for r in rows])
                prev.row_pages.extend(row_pages)
                prev.pages.extend(p for p in t.pages if p not in prev.pages)
        if not joined:
            result.append(replace(t, rows=[list(r) for r in t.rows], pages=list(t.pages),
                                  row_pages=list(t.row_pages) or [t.pages[0]] * len(t.rows)))
        prev_index = i
    return result


def page_position_flags(tables_per_page: list[list[TableData]]) -> tuple[list[TableData], set[int], set[int]]:
    """Flatten per-page table lists, recording first/last-on-page indexes."""
    flat: list[TableData] = []
    first: set[int] = set()
    last: set[int] = set()
    for page_tables in tables_per_page:
        if not page_tables:
            continue
        first.add(len(flat))
        flat.extend(page_tables)
        last.add(len(flat) - 1)
    return flat, first, last
