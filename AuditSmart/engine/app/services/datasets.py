"""Dataset lifecycle: upload sessions, storage, parse and validation jobs (prompt 3.2).

Status flow: uploading -> uploaded -> parsing -> parsed -> validated | blocked
(``failed`` if a job errors). Downstream services must call ``assert_usable``.
"""

from __future__ import annotations

import csv
import shutil
import zipfile
from pathlib import Path
from typing import Any, BinaryIO

from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.db import session_factory
from app.core.logging import log_event
from app.models import Dataset
from app.models import ValidationError as ValidationErrorRow
from app.services import jobs
from app.services.importer import (
    MappingError,
    copy_stream,
    normalise_override,
    parse_to_parquet,
    read_headers,
    sha256_file,
    suggest_mapping,
)
from app.services.validation import ValidationReport, validate_parquet

IMPLEMENTED_BY_PROMPT = "3.2"

ALLOWED_SUFFIXES = (".csv", ".txt", ".xlsx", ".xlsm")


class DatasetError(Exception):
    """User-facing problem (message is plain English)."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class DatasetBlocked(DatasetError):
    pass


def _headers(path: Path) -> list[str]:
    """The file's header row; an unreadable file is a 422 with a plain reason (D56)."""
    try:
        return read_headers(path)
    except Exception as exc:
        raise DatasetError(_read_error(exc), 422) from None


def _checked_override(headers: list[str], override: object) -> dict[str, str] | None:
    """D56: validate a mapping override against the file's headers before any job starts."""
    if override is None:
        return None
    try:
        return normalise_override(override, headers)
    except MappingError as exc:
        raise DatasetError(exc.message, 422) from None


def _read_error(exc: BaseException) -> str:
    """Plain-English reason a file could not be read (D56). No stack trace, no row values."""
    if isinstance(exc, MappingError):
        return exc.message
    if isinstance(exc, UnicodeDecodeError):
        return ("The file is not UTF-8 text (a character near byte "
                f"{exc.start} could not be read). In Excel use Save As > 'CSV UTF-8', "
                "or upload the .xlsx file, then try again.")
    if isinstance(exc, csv.Error):
        return f"The CSV file could not be read ({exc}). Check the quotes and separators."
    if isinstance(exc, zipfile.BadZipFile) or type(exc).__name__ == "InvalidFileException":
        return "The Excel file could not be opened. Save it again as .xlsx (or CSV UTF-8)."
    if isinstance(exc, ValueError):
        first = (str(exc).splitlines() or [""])[0][:200]
        return f"The file could not be read: {first or type(exc).__name__}."
    return (f"{type(exc).__name__}: the file could not be read. Check the file and try "
            "again.")


def _root() -> Path:
    return get_settings().storage_path


def source_path(ds: Dataset) -> Path:
    suffix = Path(ds.file_name).suffix.lower() or ".csv"
    return _root() / "datasets" / ds.id / f"source{suffix}"


def chunk_dir(dataset_id: str) -> Path:
    return _root() / "uploads" / dataset_id


def parquet_path(dataset_id: str) -> Path:
    return _root() / "parquet" / f"{dataset_id}.parquet"


def _check_name(file_name: str) -> str:
    name = Path(file_name).name
    if not name or Path(name).suffix.lower() not in ALLOWED_SUFFIXES:
        raise DatasetError("Upload a CSV or Excel (.xlsx) file.", 415)
    return name


def get_dataset(dataset_id: str) -> Dataset:
    with session_factory()() as s:
        ds = s.get(Dataset, dataset_id)
        if ds is None:
            raise DatasetError("Dataset not found.", 404)
        return ds


def _update(dataset_id: str, **values: Any) -> None:
    with session_factory()() as s:
        ds = s.get(Dataset, dataset_id)
        assert ds is not None
        for k, v in values.items():
            setattr(ds, k, v)
        s.commit()


# ---------------------------------------------------------------- upload protocol
def start_upload(engagement_id: str, file_name: str, size_bytes: int, kind: str,
                 user_id: str) -> Dataset:
    name = _check_name(file_name)
    if size_bytes > get_settings().max_upload_bytes:
        raise DatasetError(
            f"The file is larger than the {get_settings().max_upload_mb} MB limit.", 413)
    with session_factory()() as s:
        ds = Dataset(engagement_id=engagement_id, file_name=name, size_bytes=size_bytes,
                     kind=kind, status="uploading", created_by=user_id)
        s.add(ds)
        s.commit()
    chunk_dir(ds.id).mkdir(parents=True, exist_ok=True)
    log_event("upload.started", dataset_id=ds.id, engagement_id=engagement_id, bytes=size_bytes)
    return ds


def put_chunk(dataset_id: str, index: int, data: bytes) -> int:
    ds = get_dataset(dataset_id)
    if ds.status != "uploading":
        raise DatasetError("This upload is already complete.", 409)
    if index < 0 or index > 100_000:
        raise DatasetError("Chunk index is out of range.", 400)
    if len(data) > get_settings().upload_chunk_bytes:
        raise DatasetError(
            f"Each chunk must be at most {get_settings().upload_chunk_mb} MB.", 413)
    d = chunk_dir(dataset_id)
    received = sum(p.stat().st_size for p in d.glob("chunk_*") if p.name != f"chunk_{index:06d}")
    if received + len(data) > (ds.size_bytes or 0):
        raise DatasetError("More data was sent than the declared file size.", 413)
    (d / f"chunk_{index:06d}").write_bytes(data)
    count = len(list(d.glob("chunk_*")))
    _update(dataset_id, chunks_received=count)
    return count


def complete_upload(dataset_id: str, *, user_id: str, mapping_override: object,
                    expected_sha256: str | None = None) -> tuple[Dataset, str]:
    ds = get_dataset(dataset_id)
    if ds.status != "uploading":
        raise DatasetError("This upload is already complete.", 409)
    d = chunk_dir(dataset_id)
    parts = sorted(d.glob("chunk_*"))
    indices = [int(p.name.removeprefix("chunk_")) for p in parts]
    if not parts or indices != list(range(len(parts))):
        raise DatasetError("Some chunks are missing; send every chunk from 0 upwards.", 409)
    dest = source_path(ds)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as out:
        for p in parts:
            with p.open("rb") as f:
                shutil.copyfileobj(f, out, 1 << 20)
    size = dest.stat().st_size
    if size != ds.size_bytes:
        dest.unlink()
        raise DatasetError(
            f"The file received is {size} bytes but {ds.size_bytes} were declared.", 409)
    digest = sha256_file(dest)
    if expected_sha256 and expected_sha256.lower() != digest:
        dest.unlink()
        raise DatasetError("The file changed in transit (SHA-256 does not match). Upload again.",
                           409)
    try:  # D56: a bad mapping is refused before the chunks go, so complete can be retried
        headers = _headers(dest)
        override = _checked_override(headers, mapping_override)
    except DatasetError:
        dest.unlink()
        raise
    shutil.rmtree(d, ignore_errors=True)
    _update(dataset_id, sha256=digest, storage_ref=str(dest), status="uploaded",
            mapping=suggest_mapping(headers, override))
    job_id = start_parse(dataset_id, user_id=user_id, mapping_override=override,
                         prevalidated=True)
    return get_dataset(dataset_id), job_id


def upload_stream(engagement_id: str, file_name: str, stream: BinaryIO, kind: str,
                  user_id: str, mapping_override: object) -> tuple[Dataset, str]:
    """Single-request upload (multipart) – streamed to storage in 1 MB chunks."""
    name = _check_name(file_name)
    with session_factory()() as s:
        ds = Dataset(engagement_id=engagement_id, file_name=name, kind=kind,
                     status="uploading", created_by=user_id)
        s.add(ds)
        s.commit()
    dest = source_path(ds)
    try:
        size, digest = copy_stream(stream, dest, get_settings().max_upload_bytes)
    except ValueError as exc:
        _update(ds.id, status="failed")
        raise DatasetError(str(exc), 413) from None
    try:
        headers = _headers(dest)
        override = _checked_override(headers, mapping_override)
    except DatasetError:  # D56: nothing half-made is left behind
        dest.unlink(missing_ok=True)
        _update(ds.id, status="failed", size_bytes=size, sha256=digest)
        raise
    _update(ds.id, sha256=digest, size_bytes=size, storage_ref=str(dest), status="uploaded",
            mapping=suggest_mapping(headers, override))
    log_event("upload.completed", dataset_id=ds.id, bytes=size, sha256=digest)
    job_id = start_parse(ds.id, user_id=user_id, mapping_override=override, prevalidated=True)
    return get_dataset(ds.id), job_id


# ---------------------------------------------------------------- parse / validate jobs
def start_parse(dataset_id: str, *, user_id: str | None, mapping_override: object,
                prevalidated: bool = False) -> str:
    """Start the parse job. The override is checked against the file first (D56), so a bad
    mapping is a synchronous 422 and the dataset keeps its status."""
    ds = get_dataset(dataset_id)
    if ds.storage_ref is None:
        raise DatasetError("The file has not been uploaded yet.", 409)
    if not prevalidated and mapping_override is not None:
        mapping_override = _checked_override(_headers(Path(ds.storage_ref)), mapping_override)
    _update(dataset_id, status="parsing")
    return jobs.enqueue("parse", {"dataset_id": dataset_id, "mapping_override": mapping_override},
                        engagement_id=ds.engagement_id, created_by=user_id)


@jobs.task("parse")
def parse_task(job_id: str, *, dataset_id: str, mapping_override: object = None) -> str:
    ds = get_dataset(dataset_id)
    src = Path(ds.storage_ref or "")
    est_rows = max(1, src.stat().st_size // 110) if src.exists() else 1  # ~110 bytes per line
    try:
        # idempotent for an already checked override; catches jobs queued before 0.2.2 (D56)
        override = (None if mapping_override is None
                    else normalise_override(mapping_override, read_headers(src)))
        res = parse_to_parquet(
            src, parquet_path(dataset_id), kind=ds.kind,
            override=override, chunk_rows=get_settings().parse_chunk_rows,
            progress=lambda rows: jobs.set_progress(job_id, min(95, 5 + 90 * rows // est_rows)))
    except jobs.JobCancelled:
        _update(dataset_id, status="failed")
        raise
    except Exception as exc:  # D56: the job error says why, in plain English
        _update(dataset_id, status="failed")
        log_event("dataset.parse_failed", dataset_id=dataset_id, error_type=type(exc).__name__)
        raise DatasetError(_read_error(exc), 422) from None
    _update(dataset_id, status="parsed", rows=res.rows, total_dr=res.total_dr,
            total_cr=res.total_cr, parquet_ref=str(parquet_path(dataset_id)),
            mapping=res.mapping, profile=res.profile())
    with session_factory()() as s:  # new parse invalidates any earlier validation
        s.execute(delete(ValidationErrorRow).where(ValidationErrorRow.dataset_id == dataset_id))
        s.commit()
    log_event("dataset.parsed", dataset_id=dataset_id, rows=res.rows, chunks=res.chunks)
    return f"dataset:{dataset_id}"


def _persist(dataset_id: str, report: ValidationReport) -> None:
    with session_factory()() as s:
        s.execute(delete(ValidationErrorRow).where(ValidationErrorRow.dataset_id == dataset_id))
        for i in report.issues:
            s.add(ValidationErrorRow(dataset_id=dataset_id, severity=i.severity, code=i.code,
                                     field=i.field, rows=i.rows, row_count=i.row_count,
                                     message=i.message, guidance=i.guidance))
        ds = s.get(Dataset, dataset_id)
        assert ds is not None
        ds.status = "blocked" if report.blocked else "validated"
        ds.profile = {**(ds.profile or {}), "validation": report.summary()}
        s.commit()


def run_validation(dataset_id: str, tb_dataset_id: str | None = None) -> ValidationReport:
    ds = get_dataset(dataset_id)
    if ds.parquet_ref is None or ds.status in ("uploading", "uploaded", "parsing"):
        raise DatasetError("The file is still being read. Try again when parsing finishes.", 409)
    tb_path = None
    if tb_dataset_id:
        tb = get_dataset(tb_dataset_id)
        if tb.engagement_id != ds.engagement_id or tb.kind != "TB" or tb.parquet_ref is None:
            raise DatasetError("The trial balance must be a parsed TB file in this engagement.",
                               400)
        tb_path = Path(tb.parquet_ref)
    missing = list((ds.profile or {}).get("missing_columns", []))
    report = validate_parquet(Path(ds.parquet_ref), kind=ds.kind, missing_cols=missing,
                              tb_path=tb_path)
    _persist(dataset_id, report)
    log_event("dataset.validated", dataset_id=dataset_id, critical=report.critical,
              warnings=report.warnings)
    return report


def start_validation(dataset_id: str, *, user_id: str | None,
                     tb_dataset_id: str | None = None) -> str:
    ds = get_dataset(dataset_id)
    if ds.parquet_ref is None:
        raise DatasetError("The file is still being read. Try again when parsing finishes.", 409)

    return jobs.enqueue("validate", {"dataset_id": dataset_id, "tb_dataset_id": tb_dataset_id},
                        engagement_id=ds.engagement_id, created_by=user_id)


@jobs.task("validate")
def validate_task(job_id: str, *, dataset_id: str, tb_dataset_id: str | None = None) -> str:
    jobs.set_progress(job_id, 5)
    run_validation(dataset_id, tb_dataset_id)
    return f"dataset:{dataset_id}:validation"


def list_errors(dataset_id: str) -> list[ValidationErrorRow]:
    with session_factory()() as s:
        return list(s.execute(select(ValidationErrorRow).where(
            ValidationErrorRow.dataset_id == dataset_id).order_by(ValidationErrorRow.id)
        ).scalars())


def assert_usable(dataset_id: str) -> Dataset:
    """Guard for downstream services: the dataset must be validated with no critical errors."""
    ds = get_dataset(dataset_id)
    if ds.status == "blocked":
        n = sum(1 for e in list_errors(dataset_id) if e.severity == "critical")
        raise DatasetBlocked(
            f"This dataset has {n} critical validation error(s). Fix them and upload the "
            "corrected file before running this step.", 409)
    if ds.status != "validated":
        raise DatasetBlocked("Validate this dataset first (POST /v1/datasets/{id}/validate).",
                             409)
    return ds
