"""Input-VAT check endpoints: FTA Decisions 13 and 17 of 2026 (SPEC 3.8, prompt 3.12).

PUT  /v1/engagements/{id}/supplier-register   CSV upload; replaces the register
GET  /v1/engagements/{id}/supplier-register
PUT  /v1/engagements/{id}/expense-mapping     account -> Decision 17 category
GET  /v1/engagements/{id}/expense-mapping
POST /v1/input-vat-check                      -> 202, background job
GET  /v1/input-vat-check/{id}                 stored result
GET  /v1/input-vat-check/{id}/exceptions      paginated, optional ?check=
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from app.api.v1.deps import CurrentUser, DbSession, check_membership
from app.schemas.input_vat import InputVatAccepted, InputVatCreate, MappingIn
from app.services import datasets as ds_svc
from app.services import input_vat as svc

router = APIRouter(tags=["input-vat"])
EDITORS = ("Partner", "Manager", "Senior", "Staff")
MAX_BYTES = 5 * 1024 * 1024
Check = Literal["unverified_supplier", "spend_threshold", "risk_indicator_unexplained",
                "employee_expense", "staff_cost_unmapped"]


def _err(exc: svc.InputVatError) -> HTTPException:
    return HTTPException(exc.status_code, exc.message)


@router.put("/engagements/{engagement_id}/supplier-register",
            summary="Upload the supplier verification register (CSV, replaces)")
def put_register(engagement_id: str, user: CurrentUser, db: DbSession,
                 file: Annotated[UploadFile, File()]) -> dict[str, Any]:
    check_membership(db, user, engagement_id, EDITORS)
    data = file.file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "The register is larger than 5 MB.")
    try:
        suppliers, errors = svc.parse_register_csv(data)
    except svc.InputVatError as exc:
        raise _err(exc) from None
    if errors:
        raise HTTPException(422, {"message": "Fix these rows and upload again; nothing was "
                                             "saved.", "errors": errors})
    n = svc.replace_register(engagement_id, suppliers, user_id=user.user_id)
    return {"engagement_id": engagement_id, "suppliers": n}


@router.get("/engagements/{engagement_id}/supplier-register")
def get_register(engagement_id: str, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    check_membership(db, user, engagement_id)
    items = svc.register_view(engagement_id)
    return {"engagement_id": engagement_id, "total": len(items), "items": items}


@router.put("/engagements/{engagement_id}/expense-mapping",
            summary="Map expense accounts to the Decision 17 categories (replaces)")
def put_mapping(engagement_id: str, body: MappingIn, user: CurrentUser,
                db: DbSession) -> dict[str, Any]:
    check_membership(db, user, engagement_id, EDITORS)
    try:
        mapping = svc.replace_mapping(engagement_id, [i.model_dump() for i in body.items],
                                      user_id=user.user_id)
    except svc.InputVatError as exc:
        raise _err(exc) from None
    return {"engagement_id": engagement_id, "mapping": mapping,
            "categories": svc.categories()}


@router.get("/engagements/{engagement_id}/expense-mapping")
def get_mapping(engagement_id: str, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    check_membership(db, user, engagement_id)
    return {"engagement_id": engagement_id, "mapping": svc.load_mapping(engagement_id),
            "categories": svc.categories()}


@router.post("/input-vat-check", status_code=202, response_model=InputVatAccepted,
             summary="Run the Decision 13 / 17 input-VAT checks as a background job")
def create_run(body: InputVatCreate, user: CurrentUser, db: DbSession) -> InputVatAccepted:
    try:
        ds = ds_svc.get_dataset(body.dataset_id)
    except ds_svc.DatasetError as exc:
        raise HTTPException(exc.status_code, exc.message) from None
    check_membership(db, user, ds.engagement_id)
    over = ({"effective_date_override": body.effective_date_override}
            if body.effective_date_override else {})
    try:
        run_id, job_id = svc.start_run(ds.id, over, user_id=user.user_id)
    except ds_svc.DatasetError as exc:
        raise HTTPException(exc.status_code, exc.message) from None
    except svc.InputVatError as exc:  # pragma: no cover - schema validates the date first
        raise _err(exc) from None
    return InputVatAccepted(input_vat_run_id=run_id, job_id=job_id,
                            status_url=f"/v1/jobs/{job_id}",
                            result_url=f"/v1/input-vat-check/{run_id}")


@router.get("/input-vat-check/{run_id}", summary="Input-VAT run result")
def read_run(run_id: str, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    try:
        eng, out = svc.get_run(run_id)
    except svc.InputVatError as exc:
        raise _err(exc) from None
    check_membership(db, user, eng)
    return out


@router.get("/input-vat-check/{run_id}/exceptions", summary="Exceptions, paginated")
def read_exceptions(run_id: str, user: CurrentUser, db: DbSession,
                    check: Check | None = None,
                    offset: Annotated[int, Query(ge=0)] = 0,
                    limit: Annotated[int, Query(ge=1, le=1000)] = 100) -> dict[str, Any]:
    try:
        eng, total, items = svc.list_exceptions(run_id, check=check, offset=offset,
                                                limit=limit)
    except svc.InputVatError as exc:
        raise _err(exc) from None
    check_membership(db, user, eng)
    return {"input_vat_run_id": run_id, "total": total, "offset": offset, "limit": limit,
            "items": items}
