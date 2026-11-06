"""Sampling endpoints (SPEC 3.3, prompt 3.3): POST /v1/sample, GET /v1/samples/{id}."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi import status as http

from app.api.v1.deps import CurrentUser, DbSession, check_membership
from app.schemas.sampling import SampleCreate, SampleOut
from app.services import datasets as ds_svc
from app.services import sampling as svc
from app.services.rules import engagement_scope

router = APIRouter(tags=["sampling"])


@router.post("/sample", response_model=SampleOut, status_code=http.HTTP_201_CREATED)
def create_sample(body: SampleCreate, user: CurrentUser, db: DbSession) -> SampleOut:
    try:
        ds = ds_svc.get_dataset(body.dataset_id)
    except ds_svc.DatasetError as exc:
        raise HTTPException(exc.status_code, exc.message) from None
    check_membership(db, user, ds.engagement_id)
    req = svc.SampleRequest(**body.model_dump(exclude={"dataset_id"}))
    try:
        with engagement_scope(ds.engagement_id):  # D42: the engagement's firm rules
            out = svc.create_sample(ds.id, req, user_id=user.user_id)
    except ds_svc.DatasetError as exc:
        raise HTTPException(exc.status_code, exc.message) from None
    except svc.SamplingError as exc:
        raise HTTPException(422, str(exc)) from None
    return SampleOut.model_validate(out)


@router.get("/samples/{sample_id}", response_model=SampleOut)
def read_sample(sample_id: str, user: CurrentUser, db: DbSession) -> SampleOut:
    try:
        engagement_id, out = svc.get_sample(sample_id)
    except svc.SamplingError as exc:
        raise HTTPException(http.HTTP_404_NOT_FOUND, str(exc)) from None
    check_membership(db, user, engagement_id)
    return SampleOut.model_validate(out)
