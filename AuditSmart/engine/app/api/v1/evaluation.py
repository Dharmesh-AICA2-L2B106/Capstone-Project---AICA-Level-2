"""Output VAT and evaluation endpoints (SPEC 3.3, prompt 3.5).

POST /v1/vat-check -> 200, output/input VAT recalculation and TRN checks
POST /v1/evaluate  -> 200, MUS (classic) or ratio evaluation of a stored sample
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.v1.deps import CurrentUser, DbSession, check_membership
from app.schemas.evaluation import EvaluateCreate, EvaluationOut, VatCheckCreate, VatCheckOut
from app.services import datasets as ds_svc
from app.services import evaluation as ev
from app.services import sampling as smp_svc
from app.services import vat as vat_svc
from app.services.rules import engagement_scope

router = APIRouter(tags=["vat-evaluation"])


@router.post("/vat-check", response_model=VatCheckOut, summary="Output VAT and TRN checks")
def vat_check(body: VatCheckCreate, user: CurrentUser, db: DbSession) -> VatCheckOut:
    try:
        ds = ds_svc.get_dataset(body.dataset_id)
        check_membership(db, user, ds.engagement_id)
        with engagement_scope(ds.engagement_id):  # D42
            out = vat_svc.vat_check_for_dataset(ds.id, sides=body.sides)
    except ds_svc.DatasetError as exc:
        raise HTTPException(exc.status_code, exc.message) from None
    except vat_svc.VatError as exc:
        raise HTTPException(422, str(exc)) from None
    return VatCheckOut.model_validate(out)


@router.post("/evaluate", response_model=EvaluationOut, summary="Evaluate a sample (ISA 450)")
def evaluate(body: EvaluateCreate, user: CurrentUser, db: DbSession) -> EvaluationOut:
    try:
        engagement_id, _ = smp_svc.get_sample(body.sample_id)
    except smp_svc.SamplingError as exc:
        raise HTTPException(404, str(exc)) from None
    check_membership(db, user, engagement_id)
    try:
        with engagement_scope(engagement_id):  # D42
            out = ev.evaluate_sample(body.sample_id, [i.model_dump() for i in body.items],
                                     method=body.method,
                                     tm_override=body.tolerable_misstatement,
                                     user_id=user.user_id)
    except ev.EvaluationError as exc:
        raise HTTPException(422, str(exc)) from None
    return EvaluationOut.model_validate(out)
