"""Working paper endpoints (SPEC 3.3, prompt 3.6).

POST /v1/workpaper              -> 201, builds and stores the 11-sheet Excel working paper
POST /v1/workpaper/jobs         -> 202, the same build as a background job (prompt 3.11)
GET  /v1/workpapers/{id}        -> metadata (manifest of included results)
GET  /v1/workpapers/{id}/file   -> the .xlsx
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.api.v1.deps import CurrentUser, DbSession, check_membership
from app.schemas.workpaper import WorkpaperCreate, WorkpaperOut
from app.services import jobs
from app.services import workpaper as wp_svc
from app.services.rules import engagement_scope

router = APIRouter(tags=["workpaper"])
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.post("/workpaper", status_code=201, response_model=WorkpaperOut,
             summary="Generate the Excel working paper (ISA 230)")
def create_workpaper(body: WorkpaperCreate, user: CurrentUser, db: DbSession) -> WorkpaperOut:
    member = check_membership(db, user, body.engagement_id)
    try:
        with engagement_scope(body.engagement_id):  # D42
            out = wp_svc.generate(
                engagement_id=body.engagement_id, wp_ref=body.wp_ref, user_id=user.user_id,
                role=member.role, sample_id=body.sample_id, je_run_id=body.je_run_id,
                input_vat_run_id=body.input_vat_run_id, reviewer=body.reviewer,
                stale_overrides=[o.model_dump() for o in body.stale_overrides])
    except wp_svc.WorkpaperError as exc:
        raise HTTPException(exc.status_code, exc.message) from None
    return WorkpaperOut.model_validate(out)


@router.post("/workpaper/jobs", status_code=202,
             summary="Generate the working paper as a background job (large exports)")
def create_workpaper_job(body: WorkpaperCreate, user: CurrentUser,
                         db: DbSession) -> dict[str, str]:
    member = check_membership(db, user, body.engagement_id)
    job_id = jobs.enqueue("workpaper", {
        "engagement_id": body.engagement_id, "wp_ref": body.wp_ref, "user_id": user.user_id,
        "role": member.role, "sample_id": body.sample_id, "je_run_id": body.je_run_id,
        "input_vat_run_id": body.input_vat_run_id, "reviewer": body.reviewer,
        "stale_overrides": [o.model_dump() for o in body.stale_overrides]},
        engagement_id=body.engagement_id, created_by=user.user_id)
    return {"job_id": job_id, "status_url": f"/v1/jobs/{job_id}"}


def _load(workpaper_id: str, user: CurrentUser, db: DbSession) -> tuple[dict[str, object], str]:
    try:
        eng, meta, path = wp_svc.get_workpaper(workpaper_id)
    except wp_svc.WorkpaperError as exc:
        raise HTTPException(exc.status_code, exc.message) from None
    check_membership(db, user, eng)
    return meta, str(path)


@router.get("/workpapers/{workpaper_id}", response_model=WorkpaperOut)
def get_workpaper(workpaper_id: str, user: CurrentUser, db: DbSession) -> WorkpaperOut:
    meta, _ = _load(workpaper_id, user, db)
    return WorkpaperOut.model_validate(meta)


@router.get("/workpapers/{workpaper_id}/file", response_class=FileResponse)
def download_workpaper(workpaper_id: str, user: CurrentUser, db: DbSession) -> FileResponse:
    meta, path = _load(workpaper_id, user, db)
    return FileResponse(path, media_type=XLSX, filename=f"{meta['wp_ref']}.xlsx")
