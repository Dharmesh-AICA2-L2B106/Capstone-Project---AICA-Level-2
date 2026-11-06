"""Dataset endpoints (SPEC 3.3): upload (chunked or single), validate, errors, rows."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any, Literal

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi import status as http

from app.api.v1.deps import CurrentUser, DbSession, check_membership
from app.core.config import get_settings
from app.models import Dataset
from app.schemas.datasets import (
    ChunkAck,
    DatasetAccepted,
    DatasetOut,
    JobAccepted,
    MappingUpdate,
    RowsPage,
    UploadComplete,
    UploadSession,
    UploadStart,
    ValidateRequest,
    ValidationIssueOut,
    ValidationResult,
)
from app.services import datasets as svc
from app.services.importer import AMOUNT_TYPE
from app.services.validation import ROW_NOTE

router = APIRouter(tags=["datasets"])
UPLOADERS = ("Admin", "Partner", "Manager", "Senior", "Staff")


def _err(exc: svc.DatasetError) -> HTTPException:
    return HTTPException(exc.status_code, exc.message)


def _dataset_for(dataset_id: str, user: CurrentUser, db: DbSession) -> Dataset:
    try:
        ds = svc.get_dataset(dataset_id)
    except svc.DatasetError as exc:
        raise _err(exc) from None
    check_membership(db, user, ds.engagement_id)
    return ds


MemberDataset = Annotated[Dataset, Depends(_dataset_for)]


def require_validated_dataset(ds: MemberDataset) -> Dataset:
    """Downstream guard: 409 while the dataset has critical errors or is not validated."""
    try:
        return svc.assert_usable(ds.id)
    except svc.DatasetError as exc:
        raise _err(exc) from None


ValidatedDataset = Annotated[Dataset, Depends(require_validated_dataset)]


def _out(ds: Dataset) -> DatasetOut:
    return DatasetOut(
        id=ds.id, engagement_id=ds.engagement_id, file_name=ds.file_name, kind=ds.kind,
        status=ds.status, sha256=ds.sha256, size_bytes=ds.size_bytes, rows=ds.rows,
        total_dr=None if ds.total_dr is None else str(ds.total_dr),
        total_cr=None if ds.total_cr is None else str(ds.total_cr),
        mapping=ds.mapping, profile=ds.profile, created_at=ds.created_at)


def _accepted(ds: Dataset, job_id: str) -> DatasetAccepted:
    return DatasetAccepted(dataset_id=ds.id, job_id=job_id, sha256=ds.sha256,
                           mapping_suggestion=ds.mapping, profile=ds.profile, status=ds.status)


# ------------------------------------------------------------ chunked upload protocol
@router.post("/uploads", status_code=http.HTTP_201_CREATED, response_model=UploadSession,
             summary="Start a chunked upload (returns the dataset id and chunk size)")
def start_upload(body: UploadStart, user: CurrentUser, db: DbSession) -> UploadSession:
    check_membership(db, user, body.engagement_id, UPLOADERS)
    try:
        ds = svc.start_upload(body.engagement_id, body.file_name, body.size_bytes, body.kind,
                              user.user_id)
    except svc.DatasetError as exc:
        raise _err(exc) from None
    s = get_settings()
    return UploadSession(dataset_id=ds.id, chunk_size_bytes=s.upload_chunk_bytes,
                         max_upload_bytes=s.max_upload_bytes, status=ds.status)


@router.put("/uploads/{dataset_id}/chunks/{index}", response_model=ChunkAck,
            summary="Send one chunk (raw bytes, index from 0)")
async def put_chunk(index: int, request: Request, ds: MemberDataset) -> ChunkAck:
    limit = get_settings().upload_chunk_bytes
    data = bytearray()
    async for part in request.stream():
        data.extend(part)
        if len(data) > limit:
            raise HTTPException(413, f"Each chunk must be at most {get_settings().upload_chunk_mb}"
                                     " MB.")
    try:
        count = svc.put_chunk(ds.id, index, bytes(data))
    except svc.DatasetError as exc:
        raise _err(exc) from None
    return ChunkAck(dataset_id=ds.id, index=index, chunks_received=count)


@router.post("/uploads/{dataset_id}/complete", status_code=http.HTTP_202_ACCEPTED,
             response_model=DatasetAccepted,
             summary="Assemble chunks, compute SHA-256 and start the parse job")
def complete_upload(body: UploadComplete, ds: MemberDataset, user: CurrentUser
                    ) -> DatasetAccepted:
    try:
        ds2, job_id = svc.complete_upload(ds.id, user_id=user.user_id,
                                          mapping_override=body.mapping_override,
                                          expected_sha256=body.sha256)
    except (svc.DatasetError, ValueError) as exc:
        raise (_err(exc) if isinstance(exc, svc.DatasetError) else HTTPException(400, str(exc))
               ) from None
    return _accepted(ds2, job_id)


# ------------------------------------------------------------ single-request upload
@router.post("/datasets", status_code=http.HTTP_202_ACCEPTED, response_model=DatasetAccepted,
             summary="Upload a GL or TB file (async: returns job id, mapping, SHA-256)")
def upload_dataset(
    user: CurrentUser,
    db: DbSession,
    engagement_id: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    kind: Annotated[Literal["GL", "TB"], Form()] = "GL",
    mapping_override: Annotated[str | None, Form(description="JSON {field: header}")] = None,
) -> DatasetAccepted:
    check_membership(db, user, engagement_id, UPLOADERS)
    override: object = None
    if mapping_override:
        try:
            override = json.loads(mapping_override)
            assert isinstance(override, dict)
        except (ValueError, AssertionError):
            raise HTTPException(422, 'mapping_override must be a JSON object of {field: column '
                                     'header}, for example {"posting_date": "Posting Date"}.'
                                ) from None
    try:
        ds, job_id = svc.upload_stream(engagement_id, file.filename or "", file.file, kind,
                                       user.user_id, override)
    except (svc.DatasetError, ValueError) as exc:
        raise (_err(exc) if isinstance(exc, svc.DatasetError) else HTTPException(400, str(exc))
               ) from None
    return _accepted(ds, job_id)


@router.get("/datasets/{dataset_id}", response_model=DatasetOut)
def get_dataset(ds: MemberDataset) -> DatasetOut:
    return _out(svc.get_dataset(ds.id))


@router.put("/datasets/{dataset_id}/mapping", status_code=http.HTTP_202_ACCEPTED,
            response_model=JobAccepted, summary="Override the header mapping and re-parse")
def update_mapping(body: MappingUpdate, ds: MemberDataset, user: CurrentUser) -> JobAccepted:
    try:
        job_id = svc.start_parse(ds.id, user_id=user.user_id,
                                 mapping_override=body.mapping_override)
    except svc.DatasetError as exc:
        raise _err(exc) from None
    return JobAccepted(job_id=job_id, dataset_id=ds.id, status=svc.get_dataset(ds.id).status)


def _result(dataset_id: str) -> ValidationResult:
    ds = svc.get_dataset(dataset_id)
    errs = [ValidationIssueOut.model_validate(e) for e in svc.list_errors(dataset_id)]
    crit = sum(1 for e in errs if e.severity == "critical")
    return ValidationResult(dataset_id=dataset_id, status=ds.status, critical=crit,
                            warnings=len(errs) - crit, blocked=ds.status == "blocked",
                            row_note=ROW_NOTE, errors=errs)


@router.post("/datasets/{dataset_id}/validate", status_code=http.HTTP_202_ACCEPTED,
             response_model=JobAccepted | ValidationResult,
             summary="Run validation (async job; wait=true returns the results)")
def validate(ds: MemberDataset, user: CurrentUser, body: ValidateRequest | None = None,
             wait: bool = False) -> JobAccepted | ValidationResult:
    tb = body.tb_dataset_id if body else None
    try:
        if wait:
            svc.run_validation(ds.id, tb)
            return _result(ds.id)
        job_id = svc.start_validation(ds.id, user_id=user.user_id, tb_dataset_id=tb)
    except svc.DatasetError as exc:
        raise _err(exc) from None
    return JobAccepted(job_id=job_id, dataset_id=ds.id, status=svc.get_dataset(ds.id).status)


@router.get("/datasets/{dataset_id}/errors", response_model=ValidationResult)
def errors(ds: MemberDataset) -> ValidationResult:
    return _result(ds.id)


def _jsonable(v: Any) -> Any:
    """Decimals as exact strings (2 dp when exact), dates as ISO."""
    if isinstance(v, Decimal):
        two = v.quantize(Decimal("0.01"))
        return str(two) if two == v else str(v.normalize())
    if isinstance(v, date):
        return v.isoformat()
    return v


@router.get("/datasets/{dataset_id}/rows", response_model=RowsPage,
            summary="Paginated parsed rows (filters: voucher, account, user, dates, amount)")
def rows(ds: MemberDataset, offset: Annotated[int, Query(ge=0)] = 0,
         limit: Annotated[int, Query(ge=1, le=1000)] = 100, voucher_no: str | None = None,
         account_code: str | None = None, user_id: str | None = None,
         date_from: date | None = None, date_to: date | None = None,
         min_amount: Annotated[Decimal | None, Query(ge=0)] = None) -> RowsPage:
    """Filters are pushed down to the Parquet reader, so a 1M-line file is not loaded whole."""
    if ds.parquet_ref is None:
        raise HTTPException(409, "The file is still being read. Try again shortly.")
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, "date_from must be on or before date_to.")
    filters: list[tuple[str, str, Any]] = []
    for col, val in (("voucher_no", voucher_no), ("account_code", account_code),
                     ("user_id", user_id)):
        if val:
            filters.append((col, "==", val))
    if date_from:
        filters.append(("posting_date", ">=", date_from))
    if date_to:
        filters.append(("posting_date", "<=", date_to))
    table = pq.read_table(Path(ds.parquet_ref), filters=filters or None)
    if min_amount is not None:
        floor = pa.scalar(min_amount, type=AMOUNT_TYPE)
        zero = pa.scalar(Decimal(0), type=AMOUNT_TYPE)
        big = pc.or_(pc.greater_equal(pc.fill_null(table["debit"], zero), floor),
                     pc.greater_equal(pc.fill_null(table["credit"], zero), floor))
        table = table.filter(big)
    page = table.slice(offset, limit).to_pylist()
    return RowsPage(dataset_id=ds.id, total=table.num_rows, offset=offset, limit=limit,
                    rows=[{k: _jsonable(v) for k, v in r.items()} for r in page])
