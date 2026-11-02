"""Connects each tool page to its engine.

A runner receives the files, the option values (keyed by the option label shown
on screen), the output folder and the passwords the user typed, and returns a
result dict. Runners never touch Qt, so they can run in a thread or a worker
process. Several files are processed one by one; a file that fails is reported
and the others still complete.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from .services import markdown_pdf as mdp
from .services import utilities as ut
from .services.common import (Cancelled, Job, Result, UserError, open_pdf, output_path, parse_page_groups,
                              parse_pages)
from .services.ocr import LANGUAGE_CHOICES


def _pages_of(path, password) -> int:
    with open_pdf(path, password) as doc:
        return doc.page_count


def _each(job: Job, files: list[str], work: Callable[[Job, str], Result]) -> dict:
    """Run work(file) for every file; collect results and per-file errors."""
    merged = Result()
    failed: list[str] = []
    messages: list[str] = []
    n = len(files)
    for i, f in enumerate(files):
        def scaled(done, total, text, i=i, f=f):
            frac = (done / total) if total else 0
            job.progress(int((i + frac) * 1000), n * 1000, f"{Path(f).name}: {text}" if n > 1 else text)
        sub = Job(scaled, job.is_cancelled)
        try:
            r = work(sub, f)
        except Cancelled:
            raise
        except UserError as exc:
            if n == 1:
                raise
            failed.append(f"{Path(f).name}: {exc}")
            continue
        merged.files += r.files
        merged.warnings += r.warnings
        messages.append(r.message)
        if n > 1 and r.message:
            merged.details.append(r.message)
        merged.details += r.details
        if r.confirm:
            merged.confirm = merged.confirm or {"plans": {}, "lines": [], "title": r.confirm.get("title", "")}
            merged.confirm["plans"].update(r.confirm["plans"])
            merged.confirm["lines"] += r.confirm["lines"]
    if failed and not messages:
        raise UserError("No file could be processed:\n" + "\n".join(failed))
    ok = n - len(failed)
    if n == 1:
        merged.message = messages[0] if messages else ""
    else:
        merged.message = f"{ok} of {n} file(s) done." + (f" {len(failed)} failed." if failed else "")
    merged.warnings = failed + merged.warnings
    job.progress(1, 1, "Done")
    return merged.as_dict()


# ------------------------------------------------------------------ tools

def merge(job, files, opts, out_dir, passwords):
    if len(files) < 2:
        raise UserError("Add at least two PDFs to merge.")
    name = opts.get("Output file name") or "Merged.pdf"
    out = output_path(Path(files[0]), out_dir, "", ".pdf", name=name)
    return ut.merge(job, [(f, passwords.get(f, "")) for f in files], out,
                    bookmarks=opts.get("Add a bookmark for each original file", True)).as_dict()


def split(job, files, opts, out_dir, passwords):
    def work(sub, f):
        pw = passwords.get(f, "")
        total = _pages_of(f, pw)
        mode = opts.get("Split by", "Every N pages")
        if mode == "Every page":
            groups = [[p] for p in range(1, total + 1)]
        elif mode == "Page ranges":
            groups = parse_page_groups(opts.get("Page ranges", ""), total)
        else:
            n = max(1, int(opts.get("N (pages per file)", 1)))
            groups = [list(range(a, min(a + n, total + 1))) for a in range(1, total + 1, n)]
        taken: set = set()
        outs = []
        for g in groups:
            label = f"_p{g[0]}" if len(g) == 1 else f"_p{g[0]}-{g[-1]}"
            outs.append(output_path(Path(f), out_dir, label, ".pdf", taken))
        return ut.split(sub, f, pw, groups, outs)
    return _each(job, files, work)


def extract(job, files, opts, out_dir, passwords):
    def work(sub, f):
        pw = passwords.get(f, "")
        pages = parse_pages(opts.get("Pages", ""), _pages_of(f, pw), blank_means_all=False)
        return ut.extract(sub, f, pw, pages, output_path(Path(f), out_dir, "_extract", ".pdf"))
    return _each(job, files, work)


def numbering(job, files, opts, out_dir, passwords):
    def work(sub, f):
        pw = passwords.get(f, "")
        pages = parse_pages(opts.get("Pages", ""), _pages_of(f, pw))
        return ut.add_page_numbers(sub, f, pw, output_path(Path(f), out_dir, "_numbered", ".pdf"), pages,
                                   opts.get("Position", "Bottom centre"), int(opts.get("Start at", 1)),
                                   opts.get("Format", "1"), float(opts.get("Font size", 10)))
    return _each(job, files, work)


def rearrange(job, files, opts, out_dir, passwords):
    f = files[0]
    order = opts.get("_order")
    if not order:
        raise UserError("Open the PDF and arrange its pages first.")
    return ut.rearrange(job, f, passwords.get(f, ""), [tuple(o) for o in order],
                        output_path(Path(f), out_dir, "_rearranged", ".pdf")).as_dict()


def rotate(job, files, opts, out_dir, passwords):
    which = opts.get("Rotate which pages", "All pages")
    plans = opts.get("_plan")                          # approved sideways-page plan

    def work(sub, f):
        pw = passwords.get(f, "")
        out = output_path(Path(f), out_dir, "_rotated", ".pdf")
        if which.startswith("Sideways"):
            if plans is not None:
                turns = {int(k): v for k, v in plans.get(f, {}).items()}
                if not turns:
                    return Result([], f"'{Path(f).name}': every page is already upright - nothing to change.")
                return ut.apply_turns(sub, f, pw, out, turns)
            found = ut.detect_sideways(sub, f, pw)
            lines = [f"{Path(f).name}:"]
            for p, t in sorted(found["turns"].items()):
                how = "text direction" if found["methods"][p] == "text" else "OCR orientation check"
                lines.append(f"    page {p}: turn {ut.TURN_WORDS[t]}  ({how})")
            if not found["turns"]:
                lines.append("    every page is already upright")
            if found["undecided"]:
                lines.append("    could not decide (left as they are): pages "
                             + ", ".join(map(str, found["undecided"][:30])))
            r = Result(confirm={"title": "Sideways pages found", "plans": {f: found["turns"]}, "lines": lines})
            return r
        total = _pages_of(f, pw)
        selected = (parse_pages(opts.get("Page numbers", ""), total, blank_means_all=False)
                    if which == "Selected pages" else None)
        deg = ut.DIRECTIONS[opts.get("Direction", "90° clockwise")]
        return ut.apply_turns(sub, f, pw, out, {p: deg for p in ut.pages_for(which, total, selected)})
    return _each(job, files, work)


def pdf2img(job, files, opts, out_dir, passwords):
    fmt = opts.get("Format", "PNG")
    dpi = int(str(opts.get("Resolution", "200 dpi")).split()[0])
    ext = ".jpg" if fmt == "JPEG" else ".png"

    def work(sub, f):
        pw = passwords.get(f, "")
        pages = parse_pages(opts.get("Pages", ""), _pages_of(f, pw))
        folder = Path(out_dir) if out_dir else Path(f).parent
        taken: set = set()
        outs = [output_path(Path(f), str(folder), f"_page{p:03d}", ext, taken) for p in pages]
        return ut.pdf_to_images(sub, f, pw, pages, outs, fmt, dpi)
    return _each(job, files, work)


def img2pdf(job, files, opts, out_dir, passwords):
    name = opts.get("Output file name") or f"{Path(files[0]).stem}_images.pdf"
    out = output_path(Path(files[0]), out_dir, "", ".pdf", name=name)
    return ut.images_to_pdf(job, files, out, opts.get("Page size", "A4"),
                            opts.get("Orientation", "Automatic")).as_dict()


def protect(job, files, opts, out_dir, passwords):
    pw1, pw2 = opts.get("Password", ""), opts.get("Confirm password", "")
    if not pw1:
        raise UserError("Enter the password to set.")
    if pw1 != pw2:
        raise UserError("The two passwords do not match.")
    allow = opts.get("Allow", [])

    def work(sub, f):
        return ut.protect(sub, f, passwords.get(f, ""), output_path(Path(f), out_dir, "_protected", ".pdf"),
                          pw1, opts.get("Permissions password (optional)", ""),
                          "Printing" in allow, "Copying text" in allow, "Editing" in allow)
    return _each(job, files, work)


def unprotect(job, files, opts, out_dir, passwords):
    def work(sub, f):
        pw = passwords.get(f) or opts.get("Current password", "")
        return ut.remove_password(sub, f, output_path(Path(f), out_dir, "_unlocked", ".pdf"), pw)
    return _each(job, files, work)


def md2pdf(job, files, opts, out_dir, passwords):
    size = float(str(opts.get("Font size", "10.5")))

    def work(sub, f):
        return mdp.markdown_to_pdf(sub, f, output_path(Path(f), out_dir, "", ".pdf"),
                                   paper=opts.get("Page size", "A4"),
                                   landscape=opts.get("Orientation", "Portrait") == "Landscape",
                                   font_size=size, font_family=opts.get("Font", "Segoe UI"),
                                   page_numbers=opts.get("Page numbers (Page 1 of N)", True),
                                   title=opts.get("Title (optional)", ""),
                                   header_text=opts.get("Header text (optional)", ""),
                                   footer_text=opts.get("Footer text (optional)", ""))
    return _each(job, files, work)


def pdf2md(job, files, opts, out_dir, passwords):
    lang = LANGUAGE_CHOICES.get(opts.get("OCR language", "English"), "eng")

    def work(sub, f):
        pw = passwords.get(f, "")
        pages = parse_pages(opts.get("Pages", ""), _pages_of(f, pw))
        return mdp.pdf_to_markdown(sub, f, pw, output_path(Path(f), out_dir, "", ".md"), pages,
                                   detect_tables=opts.get("Detect tables", True),
                                   extract_images=opts.get("Save images next to the .md file", True),
                                   remove_edges=opts.get("Remove repeated headers / footers", True),
                                   page_markers=opts.get("Mark page breaks", False),
                                   ocr_mode=opts.get("OCR for scanned pages", "Automatic (recommended)"),
                                   ocr_lang=lang)
    return _each(job, files, work)


# ------------------------------------------------------------------ Section 2: PDF Converter Pro engine

class _CancelFlag:
    """Gives the copied engine the cancel_event it expects, backed by the job."""

    def __init__(self, job: Job):
        self.job = job

    def is_set(self) -> bool:
        return self.job.is_cancelled()

    def set(self) -> None:
        pass


def _convert(job: Job, files, opts, out_dir, passwords, output_format: str, bank: bool = False) -> dict:
    from .convert.batch import BatchCallbacks, BatchProcessor
    from .convert.ocr_engine import OcrEngine
    from .convert.settings import OCR_MODES, SHEET_MODES, WORD_MODES, ConversionSettings
    from .convert.validators import ValidationError, parse_page_range

    def key(table: dict, label: str, default: str) -> str:
        return next((k for k, v in table.items() if v == label), default)

    try:
        ranges = parse_page_range(opts.get("Pages", ""))
    except ValidationError as exc:
        raise UserError(str(exc))
    combined = bool(opts.get("One workbook for all PDFs", False)) and not bank
    common = dict(
        output_format=output_format, document_type="bank_statement" if bank else "general",
        ocr_mode=key(OCR_MODES, opts.get("OCR for scanned pages", ""), "auto"),
        ocr_language=LANGUAGE_CHOICES.get(opts.get("OCR language", "English"), "eng"),
        page_range=ranges,
        word_mode=key(WORD_MODES, opts.get("Word mode", ""), "editable"),
        sheet_mode=key(SHEET_MODES, opts.get("Worksheets", ""), "combine"),
        workbook_mode="combined" if combined else "per_pdf",
        indian_number_format=bool(opts.get("Indian number format (1,00,000)", True)),
        conflict_policy="increment")                       # never overwrite: 'name (2).xlsx'

    # One batch per output folder: results go next to each PDF unless a folder was chosen.
    groups: dict[str, list[Path]] = {}
    for f in files:
        folder = out_dir or (str(Path(files[0]).parent) if combined else str(Path(f).parent))
        groups.setdefault(folder, []).append(Path(f))

    total = len(files)
    state = {"index": 0, "name": ""}

    def stage(text: str) -> None:
        job.progress(state["index"] * 100 + 1, total * 100, f"{state['name']}: {text}" if total > 1 else text)

    def page(_page_no: int, done: int, of: int) -> None:
        frac = done / of if of else 0
        job.progress(int(state["index"] * 100 + frac * 99), total * 100, "")

    result = Result()
    failed: list[str] = []
    ocr = OcrEngine()
    offset = 0
    for folder, paths in groups.items():
        def started(i: int, p: Path, base=offset) -> None:
            state["index"], state["name"] = base + i, p.name
        callbacks = BatchCallbacks(file_started=started, stage=stage, page=page,
                                   ask_password=lambda p, retry: None if retry else passwords.get(str(p)))
        settings = ConversionSettings(output_folder=Path(folder), **common)
        summary = BatchProcessor(paths, settings, ocr, callbacks, _CancelFlag(job)).run()
        offset += len(paths)
        for r in summary.results:
            name = r.source.name
            if r.status in ("success", "warning"):
                result.files += [str(o) for o in r.outputs if str(o) not in result.files]
                if bank:
                    if r.statement_rows:
                        flag = (f"{r.statement_flags} row(s) need review - see the Review sheet"
                                if r.statement_flags else "every row proven against the running balance")
                        result.details.append(f"{name}: {r.statement_rows} transactions, {flag}.")
                    else:
                        result.details.append(f"{name}: converted as a general document.")
                else:
                    bits = [f"{r.pages_processed} page(s)", f"{r.tables_found} table(s)"]
                    if r.ocr_pages:
                        bits.append(f"{r.ocr_pages} page(s) read with OCR")
                    result.details.append(f"{name}: " + ", ".join(bits) + ".")
                result.warnings += [f"{name}: {w}" if total > 1 else w for w in r.warnings]
            elif r.status == "cancelled":
                continue
            else:
                failed.append(f"{name}: {r.error}")
        if summary.cancelled:
            raise Cancelled()
    if failed and not result.files:
        raise UserError("No file could be converted:\n" + "\n".join(failed))
    ok = total - len(failed)
    what = {"excel": "Excel", "word": "Word", "both": "Excel and Word"}[output_format]
    if bank:
        what = "balance-checked Excel"
    result.message = (f"{ok} of {total} PDF(s) converted to {what}." if total > 1
                      else f"'{Path(files[0]).name}' converted to {what}.")
    if failed:
        result.message += f" {len(failed)} failed."
    if combined and result.files:
        result.details.insert(0, "All PDFs are in one combined workbook (one sheet per PDF).")
    result.warnings = list(dict.fromkeys(failed + result.warnings))       # the engine can repeat a warning
    job.progress(1, 1, "Done")
    return result.as_dict()


def to_excel(job, files, opts, out_dir, passwords):
    return _convert(job, files, opts, out_dir, passwords, "excel")


def to_word(job, files, opts, out_dir, passwords):
    return _convert(job, files, opts, out_dir, passwords, "word")


def to_both(job, files, opts, out_dir, passwords):
    return _convert(job, files, opts, out_dir, passwords, "both")


def bank(job, files, opts, out_dir, passwords):
    return _convert(job, files, opts, out_dir, passwords, "excel", bank=True)


# ------------------------------------------------------------------ Section 3: Verify Redacted PDF

def verify(job, files, opts, out_dir, passwords):
    from .services import redaction as rd
    terms = opts.get("Values that must not appear", []) or []
    lang = LANGUAGE_CHOICES.get(opts.get("OCR language", "English"), "eng")

    def work(sub, f):
        res = rd.inspect(sub, f, passwords.get(f, ""), terms, ocr_verify=opts.get("Read scanned pages with OCR", True),
                         ocr_lang=lang)
        bad = [c for c in res["checks"] if c[0] in ("FAIL", "FOUND", "WARN")]
        r = Result([], "")
        r.details = [f"{status:<12} {check}: {detail}" for status, check, detail in res["checks"]]
        r.warnings = [f"{Path(f).name}: {check} - {detail}" if len(files) > 1 else f"{check} - {detail}"
                      for _s, check, detail in bad]
        r.message = (f"'{Path(f).name}': {len(bad)} item(s) need attention." if bad
                     else f"'{Path(f).name}': no targeted values or risky structures found.")
        return r
    return _each(job, files, work)


RUNNERS: dict[str, Callable] = {
    "merge": merge, "split": split, "extract": extract, "numbering": numbering, "rearrange": rearrange,
    "rotate": rotate, "pdf2img": pdf2img, "img2pdf": img2pdf, "protect": protect, "unprotect": unprotect,
    "md2pdf": md2pdf, "pdf2md": pdf2md,
    "to_excel": to_excel, "to_word": to_word, "to_both": to_both, "bank": bank,
    "verify": verify,
}
# Manual / Find / Smart / Review / Apply run inside the shared redaction workspace
# (app/redaction_ui.py), which calls app/services/redaction.py directly.
WORKSPACE_TOOLS = {"manual", "find", "smart", "review", "apply"}


def is_heavy(tool_id: str, opts: dict) -> bool:
    """Heavy jobs (OCR, orientation checks, conversions) run in a separate worker process."""
    if tool_id == "rotate":
        return str(opts.get("Rotate which pages", "")).startswith("Sideways") and opts.get("_plan") is None
    return tool_id in ("pdf2md", "to_excel", "to_word", "to_both", "bank")
