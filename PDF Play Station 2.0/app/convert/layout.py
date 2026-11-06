"""Geometric layout analysis shared by native-text and OCR pages.

Pipeline (all coordinates in points, origin top-left):

    words -> lines -> segments (runs of words separated by wide gaps)
          -> borderless tables (blocks of lines whose segments align in columns)
          -> reading order (one- or two-column detection)
          -> paragraphs / headings / list items

Everything here is heuristic. The heuristics are deliberately conservative:
when a structure is not clearly present, text is kept as ordinary
paragraphs rather than being forced into a table.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from typing import Optional

from .cell_values import looks_numeric, parse_date
from .models import Run, TableData, TextBlock, Word

# Gap (in multiples of the font size) that separates two table cells or two
# text columns on the same line. Normal word spacing is ~0.25-0.35 em.
SEGMENT_GAP_EM = 1.2
# Inside a detected table: gap that separates two values (> a normal space of
# ~0.28 em), and the larger gap needed between a value and a text word.
FINE_VALUE_GAP_EM = 0.35
FINE_MIXED_GAP_EM = 0.8

_BULLET = re.compile(r"^([•▪●◦‣⁃∙·*\-–])\s+")
_NUMBERED = re.compile(r"^(\(?\d{1,3}[.)]|\(?[a-zA-Z][.)]|\(?[ivxlcdmIVXLCDM]{1,6}[.)])\s+")
_SENTENCE_END = re.compile(r"[.:;!?”\"')]$")


def is_value(text: str) -> bool:
    """Amount, percentage or date - tokens that are never two halves of one cell."""
    return looks_numeric(text) or parse_date(text) is not None


def word_separator(prev: Word, cur: Word) -> str:
    """Words split only by a font change (e.g. a bold word followed by a
    comma) touch each other; those must not get an extra space."""
    return "" if cur.x0 - prev.x1 < 0.12 * min(prev.size, cur.size) else " "


def join_words(words: list[Word]) -> str:
    if not words:
        return ""
    parts = [words[0].text]
    for prev, cur in zip(words, words[1:]):
        parts.append(word_separator(prev, cur) + cur.text)
    return "".join(parts)


@dataclass
class Line:
    words: list[Word]
    column: str = "F"     # F = full width, L / R = left / right column

    @property
    def x0(self) -> float:
        return min(w.x0 for w in self.words)

    @property
    def x1(self) -> float:
        return max(w.x1 for w in self.words)

    @property
    def top(self) -> float:
        return min(w.top for w in self.words)

    @property
    def bottom(self) -> float:
        return max(w.bottom for w in self.words)

    @property
    def height(self) -> float:
        return max(self.bottom - self.top, 0.1)

    @property
    def size(self) -> float:
        return statistics.median(w.size for w in self.words)

    @property
    def bold(self) -> bool:
        return all(w.bold for w in self.words)

    @property
    def text(self) -> str:
        return join_words(self.words)

    def segments(self, gap_em: float = SEGMENT_GAP_EM, fine: bool = False) -> list["Line"]:
        """Split the line at wide gaps. ``fine`` is used only inside a block
        already recognised as a table: there, two adjacent values (amounts,
        dates) are separate cells even when the gap between them is narrow,
        as in dense 20+ column statements printed in small fonts."""
        segs: list[list[Word]] = [[self.words[0]]]
        for prev, cur in zip(self.words, self.words[1:]):
            gap = cur.x0 - prev.x1
            em = max(min(prev.size, cur.size), 4.0)
            split = gap > gap_em * em
            if not split and fine:
                prev_val, cur_val = is_value(prev.text), is_value(cur.text)
                split = (gap > FINE_VALUE_GAP_EM * em and prev_val and cur_val) or \
                        (gap > FINE_MIXED_GAP_EM * em and (prev_val or cur_val))
            if split:
                segs.append([cur])
            else:
                segs[-1].append(cur)
        return [Line(s, self.column) for s in segs]


# ---------------------------------------------------------------- lines

def build_lines(words: list[Word]) -> list[Line]:
    """Group words into visual lines by vertical overlap."""
    lines: list[Line] = []
    for w in sorted(words, key=lambda w: (round(w.top, 1), w.x0)):
        placed = False
        # Compare with the most recent lines only - words arrive sorted by top.
        for line in reversed(lines[-3:]):
            overlap = min(line.bottom, w.bottom) - max(line.top, w.top)
            if overlap >= 0.5 * min(line.height, w.height):
                line.words.append(w)
                placed = True
                break
        if not placed:
            lines.append(Line([w]))
    for line in lines:
        line.words.sort(key=lambda w: w.x0)
    lines.sort(key=lambda l: (l.top, l.x0))
    return lines


# ---------------------------------------------------------------- borderless tables

def _column_bounds(segments: list[Line], n_rows: int) -> list[tuple[float, float]]:
    """Find column x-ranges from the horizontal coverage of row segments."""
    if not segments:
        return []
    # Half-point resolution so that narrow gaps between dense columns survive.
    res = 2.0
    lo = int(min(s.x0 for s in segments) * res)
    hi = int(max(s.x1 for s in segments) * res) + 1
    coverage = [0] * (hi - lo + 1)
    for s in segments:
        for x in range(int(s.x0 * res) - lo, int(s.x1 * res) - lo + 1):
            coverage[x] += 1
    # A gap is where (almost) no row has text. Tolerate a stray overlap in
    # large tables so that one long cell does not merge two columns.
    tolerance = n_rows // 10
    cols: list[tuple[float, float]] = []
    start: Optional[int] = None
    for i, c in enumerate(coverage):
        if c > tolerance and start is None:
            start = i
        elif c <= tolerance and start is not None:
            cols.append(((start + lo) / res, (i - 1 + lo) / res))
            start = None
    if start is not None:
        cols.append(((start + lo) / res, (len(coverage) - 1 + lo) / res))
    return cols


def _assign(seg: Line, cols: list[tuple[float, float]]) -> int:
    best, best_overlap = 0, -1e9
    for i, (c0, c1) in enumerate(cols):
        overlap = min(seg.x1, c1) - max(seg.x0, c0)
        if overlap > best_overlap:
            best, best_overlap = i, overlap
    return best


def _rows_from_block(block: list[Line], gap_em: float, fine: bool = False) -> tuple[list[list[Optional[str]]], int]:
    seg_rows = [l.segments(gap_em, fine) for l in block]
    multi = [segs for segs in seg_rows if len(segs) >= 2]
    cols = _column_bounds([s for segs in multi for s in segs], len(multi))
    if len(cols) < 2:
        return [], 0
    rows: list[list[Optional[str]]] = []
    for segs in seg_rows:
        row: list[Optional[str]] = [None] * len(cols)
        for s in segs:
            i = _assign(s, cols)
            row[i] = s.text if row[i] is None else f"{row[i]} {s.text}"
        rows.append(row)
    return rows, len(cols)


def _is_tabular(rows: list[list[Optional[str]]], n_cols: int) -> bool:
    filled_rows = [r for r in rows if sum(1 for c in r if c) >= 2]
    if len(filled_rows) < 3 or len(filled_rows) < 0.6 * len(rows):
        return False
    numeric_cols = 0
    for ci in range(n_cols):
        cells = [r[ci] for r in rows[1:] if r[ci]]
        if cells and sum(looks_numeric(c) for c in cells) >= 0.5 * len(cells):
            numeric_cols += 1
    # Two-column text layouts produce two aligned "columns" of prose; only
    # accept 2-column structures when one of them is numeric.
    return n_cols >= 3 or numeric_cols >= 1


def detect_text_tables(lines: list[Line], page: int, source: str = "text",
                       gap_em: float = SEGMENT_GAP_EM) -> tuple[list[TableData], list[Line]]:
    """Detect tables without ruling lines. Returns (tables, remaining lines)."""
    tables: list[TableData] = []
    used: set[int] = set()
    i = 0
    n = len(lines)
    while i < n:
        if len(lines[i].segments(gap_em)) < 2:
            i += 1
            continue
        j = i
        block = [i]
        while j + 1 < n:
            nxt = lines[j + 1]
            gap = nxt.top - lines[j].bottom
            if gap > 2.5 * max(lines[j].height, nxt.height):
                break
            if len(nxt.segments(gap_em)) >= 2:
                block.append(j + 1)
                j += 1
                continue
            # Allow one single-segment line (a wrapped cell) between rows.
            if j + 2 < n and len(lines[j + 2].segments(gap_em)) >= 2 \
                    and lines[j + 2].top - nxt.bottom <= 2.5 * nxt.height:
                block.extend([j + 1, j + 2])
                j += 2
                continue
            break
        block_lines = [lines[k] for k in block]
        rows, n_cols = _rows_from_block(block_lines, gap_em)
        if rows and _is_tabular(rows, n_cols):
            # The block is a table: re-split it finely to separate narrowly
            # spaced value columns. Column bounds come from all rows together,
            # so a split that occurs in only a few rows cannot add a column.
            fine_rows, fine_cols = _rows_from_block(block_lines, gap_em, fine=True)
            if fine_cols > n_cols and _is_tabular(fine_rows, fine_cols):
                rows, n_cols = fine_rows, fine_cols
            x0 = min(l.x0 for l in block_lines)
            x1 = max(l.x1 for l in block_lines)
            table = TableData(rows=rows, pages=[page], row_pages=[page] * len(rows),
                              top=block_lines[0].top, source=source,
                              bbox=(x0, block_lines[0].top, x1, block_lines[-1].bottom))
            mark_header(table)
            tables.append(table)
            used.update(block)
            i = j + 1
        else:
            i += 1
    remaining = [l for k, l in enumerate(lines) if k not in used]
    return tables, remaining


def mark_header(table: TableData) -> None:
    """First row is a header when it is mostly filled with non-numeric text and
    the body contains values (numbers or at least a second row)."""
    if len(table.rows) < 2:
        return
    first = table.rows[0]
    filled = [c for c in first if c and c.strip()]
    if len(filled) < max(1, 0.5 * len(first)):
        return
    if any(looks_numeric(c) for c in filled):
        return
    body_numeric = any(looks_numeric(c) for r in table.rows[1:] for c in r if c)
    if body_numeric or len(table.rows) >= 3:
        table.header_rows = 1


# ---------------------------------------------------------------- reading order

def _find_gutter(lines: list[Line], page_width: float, gap_em: float) -> Optional[float]:
    """Return the x position of a two-column gutter, or None."""
    segs = [s for l in lines for s in l.segments(gap_em)]
    if len(segs) < 8:
        return None
    lo, hi = int(page_width * 0.3), int(page_width * 0.7)
    best_x, best_cov = None, None
    for x in range(lo, hi):
        cov = sum(1 for s in segs if s.x0 < x < s.x1)
        if best_cov is None or cov < best_cov:
            best_x, best_cov = x, cov
    if best_x is None or best_cov > 0.08 * len(segs):
        return None
    left = sum(1 for s in segs if s.x1 <= best_x)
    right = sum(1 for s in segs if s.x0 >= best_x)
    if left < 0.25 * len(segs) or right < 0.25 * len(segs):
        return None
    return float(best_x)


def reading_order(lines: list[Line], tables: list[TableData], page_width: float,
                  gap_em: float = SEGMENT_GAP_EM) -> list[object]:
    """Order text lines and tables for reading. Supports one or two columns;
    full-width lines and tables separate horizontal bands, and within each
    band the left column is read before the right column."""
    gutter = _find_gutter(lines, page_width, gap_em)
    if gutter is None:
        items: list[tuple[float, int, object]] = [(l.top, 0, l) for l in lines]
        items += [(t.top, 1, t) for t in tables]
        return [obj for _, _, obj in sorted(items, key=lambda x: (x[0], x[1]))]

    full: list[tuple[float, object]] = [(t.top, t) for t in tables]
    columns: list[Line] = []
    for line in lines:
        for seg in line.segments(gap_em):
            if seg.x1 <= gutter:
                seg.column = "L"
                columns.append(seg)
            elif seg.x0 >= gutter:
                seg.column = "R"
                columns.append(seg)
            else:
                seg.column = "F"
                full.append((seg.top, seg))
    # Merge full-width segments back into whole lines where they came from
    # one visual line (e.g. a centred title split by a wide gap).
    full.sort(key=lambda x: x[0])
    ordered: list[object] = []
    band_start = -1e9
    seps = full + [(1e9, None)]
    for top, sep in seps:
        band = [c for c in columns if band_start <= c.top < top]
        ordered += sorted((c for c in band if c.column == "L"), key=lambda c: (c.top, c.x0))
        ordered += sorted((c for c in band if c.column == "R"), key=lambda c: (c.top, c.x0))
        if sep is not None:
            ordered.append(sep)
        band_start = top
    return ordered


# ---------------------------------------------------------------- paragraphs

def _line_runs(line: Line, gap_em: float, use_tabs: bool) -> list[Run]:
    runs: list[Run] = []
    segs = line.segments(gap_em) if use_tabs else [line]
    for si, seg in enumerate(segs):
        if si:
            runs.append(Run("\t"))
        for wi, w in enumerate(seg.words):
            text = w.text if wi == 0 else word_separator(seg.words[wi - 1], w) + w.text
            prev = runs[-1] if runs and runs[-1].text != "\t" else None
            if prev and (prev.bold, prev.italic, prev.link) == (w.bold, w.italic, w.link) \
                    and abs((prev.size or 0) - w.size) < 0.6:
                prev.text += text
            else:
                if wi and prev is not None and prev.link != w.link and text.startswith(" "):
                    # keep the separating space outside the hyperlink
                    prev.text += " "
                    text = w.text
                runs.append(Run(text, w.bold, w.italic, round(w.size * 2) / 2, w.fontname or None, w.link))
    return runs


def build_blocks(ordered: list[object], body_size: float, col_bounds: dict[str, tuple[float, float]],
                 gap_em: float = SEGMENT_GAP_EM) -> list[object]:
    """Turn ordered lines into TextBlocks; TableData items pass through."""
    out: list[object] = []
    para: list[Line] = []

    gaps = [b.top - a.bottom for a, b in zip(ordered, ordered[1:])
            if isinstance(a, Line) and isinstance(b, Line) and a.column == b.column and b.top > a.bottom]
    typical_gap = statistics.median(gaps) if gaps else 2.0

    def flush() -> None:
        if para:
            out.append(_make_block(para, body_size, col_bounds, gap_em))
            para.clear()

    for item in ordered:
        if not isinstance(item, Line):
            flush()
            out.append(item)
            continue
        if para and _starts_new_paragraph(para[-1], item, body_size, typical_gap, col_bounds):
            flush()
        para.append(item)
    flush()
    return out


def _is_heading_size(size: float, body: float) -> bool:
    return size >= body * 1.15 and size - body >= 1.0


def _starts_new_paragraph(prev: Line, cur: Line, body: float, typical_gap: float,
                          col_bounds: dict[str, tuple[float, float]]) -> bool:
    if prev.column != cur.column or cur.top < prev.top:
        return True
    gap = cur.top - prev.bottom
    if gap > typical_gap + 0.45 * max(prev.height, cur.height):
        return True
    if abs(prev.size - cur.size) > 1.0 or _is_heading_size(prev.size, body) != _is_heading_size(cur.size, body):
        return True
    text = cur.text
    if _BULLET.match(text) or _NUMBERED.match(text):
        return True
    if prev.bold != cur.bold and len(prev.text) < 100:
        return True
    left, right = col_bounds.get(cur.column, col_bounds["F"])
    width = max(right - left, 1.0)
    if cur.x0 > prev.x0 + 1.5 * cur.size and len(prev.words) > 0:
        return True   # first-line indent of a new paragraph
    if prev.x1 < right - 0.15 * width and _SENTENCE_END.search(prev.text):
        return True   # short last line of the previous paragraph
    return False


def _make_block(lines: list[Line], body: float, col_bounds: dict[str, tuple[float, float]],
                gap_em: float) -> TextBlock:
    runs: list[Run] = []
    for i, line in enumerate(lines):
        line_runs = _line_runs(line, gap_em, use_tabs=(len(lines) == 1))
        if i and runs:
            last = runs[-1]
            if last.text.endswith("-") and not last.text.endswith(" -"):
                pass                             # hyphenated word wrap: keep the hyphen, no space
            else:
                last.text += " "
        runs.extend(line_runs)
    first = lines[0]
    text = "".join(r.text for r in runs)
    size = statistics.median(l.size for l in lines)
    left, right = col_bounds.get(first.column, col_bounds["F"])
    width = max(right - left, 1.0)
    x0 = min(l.x0 for l in lines)
    x1 = max(l.x1 for l in lines)

    kind, level = "paragraph", 0
    if _is_heading_size(size, body) and len(text) <= 200:
        ratio = size / body
        kind, level = "heading", (1 if ratio >= 1.6 else 2 if ratio >= 1.3 else 3)
    elif len(lines) == 1 and first.bold and len(text) <= 100 and not _SENTENCE_END.search(text.rstrip(")")):
        kind, level = "heading", 3
    elif _BULLET.match(text) or _NUMBERED.match(text):
        kind = "list_item"

    align = "left"
    left_gap, right_gap = x0 - left, right - x1
    if all(abs((l.x0 - left) - (right - l.x1)) < 0.08 * width for l in lines) and left_gap > 0.1 * width:
        align = "center"
    elif right_gap < 0.03 * width and left_gap > 0.35 * width:
        align = "right"

    indent = max(0.0, min(l.x0 for l in lines[1:]) - left) if len(lines) > 1 else max(0.0, x0 - left)
    first_indent = (first.x0 - left) - indent if len(lines) > 1 else 0.0
    if align != "left":
        indent, first_indent = 0.0, 0.0
    if kind == "list_item" and len(lines) > 1:
        # hanging indent: wrapped lines align after the marker
        first_indent = (first.x0 - left) - indent
    return TextBlock(kind=kind, runs=runs, top=first.top, level=level, align=align,
                     indent=round(indent, 1), first_line_indent=round(first_indent, 1))


def column_bounds(lines: list[Line], page_width: float) -> dict[str, tuple[float, float]]:
    bounds: dict[str, tuple[float, float]] = {}
    all_x0 = [l.x0 for l in lines] or [72.0]
    all_x1 = [l.x1 for l in lines] or [page_width - 72.0]
    bounds["F"] = (min(all_x0), max(all_x1))
    for col in ("L", "R"):
        sel = [l for l in lines if l.column == col]
        if sel:
            bounds[col] = (min(l.x0 for l in sel), max(l.x1 for l in sel))
    return bounds


def body_font_size(words: list[Word]) -> float:
    sizes = [round(w.size, 1) for w in words for _ in range(max(1, len(w.text)))]
    if not sizes:
        return 10.0
    try:
        return statistics.mode(sizes)
    except statistics.StatisticsError:
        return statistics.median(sizes)


def analyse_words(words: list[Word], page: int, page_width: float, ruled_tables: list[TableData],
                  detect_tables: bool, table_source: str = "text") -> list[object]:
    """Full layout pipeline for one page. Returns ordered TextBlocks/TableData."""
    lines = build_lines(words)
    tables = list(ruled_tables)
    if detect_tables:
        found, lines = detect_text_tables(lines, page, source=table_source)
        tables += found
    ordered = reading_order(lines, tables, page_width)
    line_items = [o for o in ordered if isinstance(o, Line)]
    bounds = column_bounds(line_items, page_width)
    return build_blocks(ordered, body_font_size(words), bounds)
