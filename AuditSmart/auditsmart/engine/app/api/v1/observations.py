"""Observation endpoints (SPEC 3.3, prompt 3.7).

POST /v1/ai/observation              -> 201, anonymise -> AI -> validated JSON draft (stored)
GET  /v1/observations/{id}           -> the observation
POST /v1/observations/{id}/review    -> accept or edit the draft (Senior/Manager/Partner)
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.v1.deps import CurrentUser, DbSession, check_membership
from app.schemas.observations import ObservationCreate, ObservationOut, ObservationReview
from app.services import observations as svc
from app.services.rules import engagement_scope

router = APIRouter(tags=["observations"])


def _err(exc: svc.ObservationError) -> HTTPException:
    return HTTPException(exc.status_code, exc.message)


@router.post("/ai/observation", status_code=201, response_model=ObservationOut,
             summary="Draft an observation with AI from an anonymised payload")
def ai_observation(body: ObservationCreate, user: CurrentUser, db: DbSession) -> ObservationOut:
    try:
        engagement_id = svc.item_engagement(body.sample_item_id)
        check_membership(db, user, engagement_id)
        with engagement_scope(engagement_id):  # D42
            out = svc.draft(sample_item_id=body.sample_item_id, user_id=user.user_id,
                            failed_attribute=body.failed_attribute, test=body.test,
                            remark=body.remark, rule_keys=body.rule_keys)
    except svc.ObservationError as exc:
        raise _err(exc) from None
    return ObservationOut.model_validate(out)


@router.get("/observations/{observation_id}", response_model=ObservationOut)
def get_observation(observation_id: str, user: CurrentUser, db: DbSession) -> ObservationOut:
    try:
        out = svc.get(observation_id)
    except svc.ObservationError as exc:
        raise _err(exc) from None
    check_membership(db, user, out["engagement_id"])
    return ObservationOut.model_validate(out)


@router.post("/observations/{observation_id}/review", response_model=ObservationOut)
def review_observation(observation_id: str, body: ObservationReview, user: CurrentUser,
                       db: DbSession) -> ObservationOut:
    try:
        cur = svc.get(observation_id)
    except svc.ObservationError as exc:
        raise _err(exc) from None
    check_membership(db, user, cur["engagement_id"], roles=svc.REVIEW_ROLES)
    out = svc.review(observation_id, user_id=user.user_id,
                     text=body.text.model_dump() if body.text else None)
    return ObservationOut.model_validate(out)
