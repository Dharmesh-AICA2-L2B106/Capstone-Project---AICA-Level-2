"""Engagement sync (Stage 5.2, D50-D55): the front end copies clients, engagements and teams.

PUT /v1/engagements/{engagement_id} -> idempotent upsert of client + engagement + full team
                                       (201 created, 200 updated)
GET /v1/engagements/{engagement_id} -> the engine's copy (team members or a firm Admin)
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Response, status

from app.api.v1.deps import CurrentUser, DbSession
from app.schemas.engagements import ID_PATTERN, EngagementOut, EngagementSync
from app.services import engagements as svc
from app.services import firm_rules
from app.services.rules import RuleError

router = APIRouter(tags=["engagements"])
EngagementId = Annotated[str, Path(min_length=1, max_length=36, pattern=ID_PATTERN)]


@router.put("/engagements/{engagement_id}", response_model=EngagementOut,
            responses={201: {"model": EngagementOut, "description": "Engagement created"}},
            summary="Create or update an engagement, its client and its whole team (sync)")
def sync_engagement(engagement_id: EngagementId, body: EngagementSync, user: CurrentUser,
                    db: DbSession, response: Response) -> EngagementOut:
    try:
        firm = firm_rules.get_firm(db, user.firm_id)
        out = svc.upsert(db, firm, engagement_id, body, user_id=user.user_id,
                         roles=user.roles)
    except (RuleError, svc.EngagementError) as exc:
        db.rollback()
        raise HTTPException(exc.status_code, exc.message) from None
    response.status_code = status.HTTP_201_CREATED if out["created"] else status.HTTP_200_OK
    return EngagementOut.model_validate(out)


@router.get("/engagements/{engagement_id}", response_model=EngagementOut,
            summary="The engine's copy of an engagement, its client and team")
def get_engagement(engagement_id: EngagementId, user: CurrentUser,
                   db: DbSession) -> EngagementOut:
    try:
        firm = firm_rules.get_firm(db, user.firm_id)
        eng = svc.check_access(db, firm.id, engagement_id, user.user_id, user.roles,
                               edit=False)
    except (RuleError, svc.EngagementError) as exc:
        raise HTTPException(exc.status_code, exc.message) from None
    return EngagementOut.model_validate(svc.view(db, eng))
