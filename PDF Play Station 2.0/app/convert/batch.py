"""Batch conversion engine, independent of the GUI.

Files are processed one after another (bounded memory). A failure in one
file is recorded and the batch continues. Cancellation is checked between
pages and between files.
"""

from __future__ import annotations

import logging
import tempfile
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from .bank_statement import StatementError, extract_statement
from .extractor import Cancelled, DocumentExtractor
from .statement_excel import write_statement_excel
from .models import BatchSummary, DocumentContent, FileResult
from .ocr_engine import OcrEngine
from .output_manager import ConflictHandler, ConflictResolver, OutputError, planned_path, save_atomically
from .pdf_inspector import PDFIUM_LOCK, PdfError, open_pdfium
from .pdf_to_excel import write_excel
from .pdf_to_word import write_word
from .settings import ConversionSettings
from .validators import ValidationError, free_disk_mb, pages_for_document

log = logging.getLogger(__name__)

MAX_PASSWORD_ATTEMPTS = 3


def _noop(*_args, **_kwargs):
    return None


@dataclass
class BatchCallbacks:
    file_started: Callable[[int, Path], None] = _noop                 # (index, path)
    stage: Callable[[str], None] = _noop                              # human-readable stage
    page: Callable[[int, int, int], None] = _noop                     # (page_no, done, total)
    file_finished: Callable[[int, FileResult], None] = _noop
    ask_password: Callable[[Path, bool], Optional[str]] = lambda path, retry: None
    resolve_conflict: Optional[ConflictResolver] = None


@dataclass
class BatchProcessor:
    files: list[Path]
    settings: ConversionSettings
    ocr: OcrEngine
    callbacks: BatchCallbacks = field(default_factory=BatchCallbacks)
    cancel_event: threading.Event = field(default_factory=threading.Event)

    def __post_init__(self) -> None:
        self.conflicts = ConflictHandler(self.settings.conflict_policy, self.callbacks.resolve_conflict)
        self.reserved: set[Path] = set()
        self.combined_docs: list[DocumentContent] = []

    @property
    def combined(self) -> bool:
        # Bank-statement workbooks are always one per PDF (each has its own balance chain).
        return self.settings.want_excel and self.settings.workbook_mode == "combined" and not self.settings.bank_mode

    def cancelled(self) -> bool:
        return self.cancel_event.is_set()

    # ------------------------------------------------------------ batch

    def run(self) -> BatchSummary:
        summary = BatchSummary(output_folder=self.settings.output_folder)
        log.info("Batch started: %d file(s), format=%s, ocr=%s, word_mode=%s, sheets=%s",
                 len(self.files), self.settings.output_format, self.settings.ocr_mode,
                 self.settings.word_mode, self.settings.sheet_mode)
        for index, path in enumerate(self.files):
            if self.cancelled():
                result = FileResult(Path(path), status="cancelled", error="Not processed (conversion cancelled).")
            else:
                self.callbacks.file_started(index, Path(path))
                result = self.process_file(Path(path))
            summary.results.append(result)
            self.callbacks.file_finished(index, result)
            log.info("File %d/%d %s: %s %s", index + 1, len(self.files), Path(path).name, result.status,
                     result.error)
        if self.combined and self.combined_docs:
            self._write_combined(summary)
        summary.cancelled = self.cancelled()
        log.info("Batch finished: %d ok, %d failed, %d skipped/cancelled",
                 summary.succeeded, summary.failed, summary.skipped)
        return summary

    def _write_combined(self, summary: BatchSummary) -> None:
        self.callbacks.stage("Creating combined Excel workbook")
        name = f"Combined_Conversion_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
        target = self.conflicts.resolve(self.settings.output_folder / name, self.reserved)
        if target is None:
            for r in summary.results:
                if r.status in ("success", "warning"):
                    r.warnings.append("Combined workbook was skipped (file already exists).")
            return
        try:
            warnings = save_atomically(target, lambda tmp: write_excel(self.combined_docs, tmp, self.settings))
            summary.combined_output = target
            for r in summary.results:
                if r.status in ("success", "warning"):
                    r.outputs.append(target)
            if warnings:
                summary.results[-1].warnings.extend(warnings)
        except Exception as exc:
            log.exception("Combined workbook failed")
            message = str(exc) if isinstance(exc, OutputError) else f"Unexpected error ({type(exc).__name__})."
            for r in summary.results:
                if r.status in ("success", "warning"):
                    r.status = "failed"
                    r.error = f"Combined Excel workbook could not be created: {message}"

    # ------------------------------------------------------------ one file

    def _open_with_password(self, path: Path) -> tuple[int, Optional[str]]:
        password: Optional[str] = None
        retry = False
        for attempt in range(MAX_PASSWORD_ATTEMPTS + 1):
            try:
                with PDFIUM_LOCK:
                    doc = open_pdfium(path, password)
                    try:
                        return len(doc), password
                    finally:
                        doc.close()
            except PdfError as exc:
                if exc.kind not in ("password", "wrong_password"):
                    raise
                if attempt == MAX_PASSWORD_ATTEMPTS:
                    raise PdfError("wrong_password", "An incorrect password was entered "
                                                     f"{MAX_PASSWORD_ATTEMPTS} times.") from exc
                retry = exc.kind == "wrong_password"
                self.callbacks.stage("Waiting for password")
                password = self.callbacks.ask_password(path, retry)
                if not password:
                    raise PdfError("password", "The PDF is password-protected and no password was provided.")
        raise PdfError("password", "The PDF is password-protected.")

    def _plan_targets(self, path: Path) -> dict[str, Optional[Path]]:
        targets: dict[str, Optional[Path]] = {}
        if self.settings.want_excel and not self.combined:
            targets["excel"] = self.conflicts.resolve(planned_path(path, self.settings, ".xlsx"), self.reserved)
        if self.settings.want_word:
            targets["word"] = self.conflicts.resolve(planned_path(path, self.settings, ".docx"), self.reserved)
        for t in targets.values():
            if t is not None:
                self.reserved.add(t)
        return targets

    def process_file(self, path: Path) -> FileResult:
        result = FileResult(path)
        s = self.settings
        try:
            self.callbacks.stage("Checking PDF")
            page_count, password = self._open_with_password(path)
            pages = pages_for_document(s.page_range, page_count)

            free = free_disk_mb(s.output_folder)
            if free is not None and free < s.min_free_disk_mb:
                raise OutputError(f"Only {free:.0f} MB of disk space is free in the output folder.")
            size_mb = path.stat().st_size / (1024 * 1024)
            if len(pages) > 500 or size_mb > 200:
                result.warnings.append(f"Large PDF ({len(pages)} pages, {size_mb:.0f} MB) - processing may take a while.")

            targets = self._plan_targets(path)
            wanted = [k for k, v in targets.items() if v is not None]
            if targets and not wanted:
                result.status = "skipped"
                result.error = "Output file already exists (skipped)."
                return result
            if not targets and not self.combined:
                result.status = "skipped"
                result.error = "No output format selected."
                return result

            with tempfile.TemporaryDirectory(prefix="pcp_") as tmp:
                def progress(page_no: int, done: int, total: int, stage: str) -> None:
                    self.callbacks.stage(f"{stage} {page_no} ({done + 1} of {total})")
                    self.callbacks.page(page_no, done, total)

                statement = None
                if s.bank_mode and targets.get("excel"):
                    def stmt_progress(message: str, done: int, total: int) -> None:
                        self.callbacks.stage(message)
                        self.callbacks.page(pages[min(done, len(pages) - 1)], done, total)
                    try:
                        statement = extract_statement(path, self.ocr, pages, s.ocr_language, password, s.ocr_mode,
                                                      s.ocr_timeout_seconds, stmt_progress, self.cancelled)
                    except StatementError as exc:
                        result.warnings.append(f"Bank-statement mode could not be applied ({exc}) - "
                                               "the Excel file was created as a general document instead.")

                content = None
                if targets.get("word") or (targets.get("excel") and statement is None) or self.combined:
                    extractor = DocumentExtractor(path, s, self.ocr, Path(tmp), password, progress, self.cancelled)
                    content = extractor.extract(pages)
                password = None   # not kept any longer than needed
                self.callbacks.page(pages[-1], len(pages), len(pages))
                if content is not None:
                    result.pages_processed = len(content.pages)
                    result.ocr_pages = len(content.ocr_pages)
                    result.tables_found = len(content.tables)
                    result.warnings.extend(content.warnings)
                if statement is not None:
                    result.pages_processed = max(result.pages_processed, len(statement.pages_used))
                    if statement.method == "ocr":
                        result.ocr_pages = max(result.ocr_pages, len(statement.pages_used))
                    result.statement_rows = len(statement.rows)
                    result.statement_flags = statement.count("Check") + statement.count("Inferred")
                    result.warnings.extend(statement.warnings)

                errors: list[str] = []
                if targets.get("excel"):
                    self.callbacks.stage("Creating Excel workbook")
                    if statement is not None:
                        self._save(targets["excel"], lambda tmp_path: write_statement_excel(statement, tmp_path),
                                   result, errors, "Excel")
                    else:
                        self._save(targets["excel"], lambda tmp_path: write_excel([content], tmp_path, s),
                                   result, errors, "Excel")
                if targets.get("word"):
                    self.callbacks.stage("Creating Word document")
                    self._save(targets["word"], lambda tmp_path: write_word(content, tmp_path, s), result, errors, "Word")
                if self.combined and content is not None:
                    for page in content.pages:
                        page.image_path = None      # temp images are deleted with this folder
                    self.combined_docs.append(content)
                skipped = [k for k, v in targets.items() if v is None]
                for k in skipped:
                    result.warnings.append(f"{k.capitalize()} output skipped because the file already exists.")

            if errors:
                result.status = "failed"
                result.error = " ".join(errors)
            else:
                result.status = "warning" if result.warnings else "success"
        except Cancelled:
            result.status = "cancelled"
            result.error = "Cancelled by the user; no output was written for this file."
        except (PdfError, ValidationError, OutputError) as exc:
            result.status = "failed"
            result.error = str(exc)
            log.warning("%s: %s", path.name, exc)
        except MemoryError:
            result.status = "failed"
            result.error = "Not enough memory to process this PDF. Try a smaller page range."
            log.exception("Out of memory on %s", path.name)
        except Exception as exc:
            result.status = "failed"
            result.error = f"Unexpected error ({type(exc).__name__}). See the log file for details."
            log.exception("Unexpected error while converting %s", path.name)
        return result

    def _save(self, target: Path, writer, result: FileResult, errors: list[str], label: str) -> None:
        try:
            result.warnings.extend(save_atomically(target, writer))
            result.outputs.append(target)
        except OutputError as exc:
            errors.append(f"{label}: {exc}")
            self.reserved.discard(target)
        except Exception as exc:
            log.exception("%s generation failed for %s", label, result.source.name)
            errors.append(f"{label} file could not be created ({type(exc).__name__}).")
            self.reserved.discard(target)
