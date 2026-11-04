"""JE testing and Benford endpoints (SPEC 3.3, prompt 3.4).

POST /v1/je-tests        -> 202, background job (poll /v1/jobs/{job_id})
GET  /v1/je-tests/{id}   -> stored result (flags, summary, calendar_hash)
POST /v1/benford         -> 200, first-digit test
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query

from app.api.v1.deps import CurrentUser, DbSession, check_membership
from app.schemas.je import BenfordCreate, BenfordOut, JeRunAccepted, JeRunCreate, JeRunOut
from app.services import benford as bf
from app.services import datasets as ds_svc
from app.services import je_tests as svc
from app.services.calendar import CalendarError
from app.services.rules import engagement_scope

router = APIRouter(tags=["je-testing"])


def _dataset(dataset_id: str, user: CurrentUser, db: DbSession) -> str:
    return _dataset_and_engagement(dataset_id, user, db)[0]


def _dataset_and_engagement(dataset_id: str, user: CurrentUser,
                            db: DbSession) -> tuple[str, str]:
    try:
        ds = ds_svc.get_dataset(dataset_id)
    except ds_svc.DatasetError as exc:
        raise HTTPException(exc.status_code, exc.message) from None
    check_membership(db, user, ds.engagement_id)
    return ds.id, ds.engagement_id


@router.post(
    "/je-tests",
    response_model=JeRunAccepted,
    status_code=202,
    summary="Run journal-entry tests (ISA 240) as a background job",
)
def create_je_run(body: JeRunCreate, user: CurrentUser, db: DbSession) -> JeRunAccepted:
    did = _dataset(body.dataset_id, user, db)
    overrides = body.parameters.model_dump(exclude_none=True)
    try:
        run_id, job_id = svc.start_je_run(did, overrides, user_id=user.user_id)
    except ds_svc.DatasetError as exc:
        raise HTTPException(exc.status_code, exc.message) from None
    except (svc.JeTestError, CalendarError) as exc:
        raise HTTPException(422, str(exc)) from None
    return JeRunAccepted(
        je_run_id=run_id,
        job_id=job_id,
        status_url=f"/v1/jobs/{job_id}",
        result_url=f"/v1/je-tests/{run_id}",
    )


@router.get("/je-tests/{run_id}", response_model=JeRunOut, summary="JE test run result")
def read_je_run(run_id: str, user: CurrentUser, db: DbSession) -> JeRunOut:
    try:
        engagement_id, out = svc.get_je_run(run_id)
    except svc.JeTestError as exc:
        raise HTTPException(404, str(exc)) from None
    check_membership(db, user, engagement_id)
    return JeRunOut.model_validate(out)


@router.get("/je-tests/{run_id}/flags", summary="Flagged lines of a run, paginated")
def read_je_flags(run_id: str, user: CurrentUser, db: DbSession,
                  flag: Annotated[str | None, Query(pattern=r"^[a-z0-9_]{1,40}$")] = None,
                  min_score: Annotated[int, Query(ge=0)] = 0,
                  offset: Annotated[int, Query(ge=0)] = 0,
                  limit: Annotated[int, Query(ge=1, le=1000)] = 100) -> dict[str, Any]:
    try:
        engagement_id, total, items = svc.list_flags(run_id, flag=flag, min_score=min_score,
                                                     offset=offset, limit=limit)
    except svc.JeTestError as exc:
        raise HTTPException(404, str(exc)) from None
    check_membership(db, user, engagement_id)
    return {"je_run_id": run_id, "total": total, "offset": offset, "limit": limit,
            "items": items}


@router.post("/benford", response_model=BenfordOut, summary="Benford first-digit test")
def benford(body: BenfordCreate, user: CurrentUser, db: DbSession) -> BenfordOut:
    did, engagement_id = _dataset_and_engagement(body.dataset_id, user, db)
    try:
        with engagement_scope(engagement_id):  # D42
            out = bf.benford_for_dataset(
                did, account_types=body.account_types, min_amount=body.min_amount
            )
    except ds_svc.DatasetError as exc:
        raise HTTPException(exc.status_code, exc.message) from None
    except bf.BenfordError as exc:
        raise HTTPException(422, str(exc)) from None
    return BenfordOut.model_validate(out)
