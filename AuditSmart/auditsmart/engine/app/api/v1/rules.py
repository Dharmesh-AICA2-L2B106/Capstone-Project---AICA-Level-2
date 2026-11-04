"""Rules Library endpoints (SPEC 3.4, prompt 3.8).

GET  /v1/rules                         -> versions (filter: rule_key, domain, status)
GET  /v1/rules/resolve/{rule_key}?on=  -> the single version effective on a date
POST /v1/rules/proposals               -> new version, status proposed (Manager+ / Tax Partner)
POST /v1/rules/{id}/approve            -> Tax Partner / Admin, mandatory comment; closes prior,
                                          audit_log, marks dependent results STALE
POST /v1/rules/{id}/reject             -> Tax Partner / Admin, mandatory comment

Multi-firm (D42): a user whose token carries a firm sees the shared defaults plus only its own
firm's versions, resolves in its firm's scope, and cannot change shared defaults here; firm
partners use /v1/firm/rules/* (app/api/v1/firm_rules.py, docs/MULTI_FIRM_APPROVAL.md).
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.v1.deps import CurrentUser, DbSession, check_membership, require_roles
from app.schemas.rules import RuleDecision, RuleOut, RuleProposal
from app.services import rules as svc

router = APIRouter(prefix="/rules", tags=["rules"])


def _err(exc: svc.RuleError) -> HTTPException:
    return HTTPException(exc.status_code, exc.message)


@router.get("", summary="List rule versions")
def list_rules(user: CurrentUser, db: DbSession, rule_key: str | None = None,
               domain: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
    return svc.list_versions(db, rule_key=rule_key, domain=domain, status=status,
                             firm_id=user.firm_id)


@router.get("/resolve/{rule_key}", response_model=RuleOut,
            summary="The single version of a rule effective on a date")
def resolve_rule(rule_key: str, user: CurrentUser, db: DbSession,
                 on: Annotated[date | None, Query()] = None,
                 engagement_id: Annotated[str | None, Query(max_length=36)] = None) -> RuleOut:
    if engagement_id is not None:
        check_membership(db, user, engagement_id)
        scope = svc.scope_for_engagement(db, engagement_id)
    else:
        scope = svc.scope_for_firm(db, user.firm_id)
    try:
        with svc.rule_scope(scope):
            r = svc.get_rule(rule_key, on)
    except svc.RuleNotFound as exc:
        raise HTTPException(404, str(exc)) from None
    except svc.RuleConflict as exc:
        raise HTTPException(409, str(exc)) from None
    return RuleOut.model_validate(svc.rule_dict(r))


@router.post("/proposals", status_code=201, response_model=RuleOut,
             dependencies=[Depends(require_roles(*svc.PROPOSER_ROLES))])
def propose_rule(body: RuleProposal, user: CurrentUser, db: DbSession) -> RuleOut:
    if user.firm_id is not None:
        raise HTTPException(403, svc.DEFAULTS_ARE_SHARED)
    try:
        row = svc.propose(db, rule_key=body.rule_key, value=body.value,
                          effective_from=body.effective_from, effective_to=body.effective_to,
                          source_url=body.source_url, source_ref=body.source_ref,
                          unit=body.unit, proposed_by=user.user_id, comment=body.comment)
    except svc.RuleError as exc:
        raise _err(exc) from None
    return RuleOut.model_validate(svc.rule_dict(svc._from_row(row)))


@router.post("/{version_id}/approve")
def approve_rule(version_id: str, body: RuleDecision, user: CurrentUser,
                 db: DbSession) -> dict[str, Any]:
    try:
        res = svc.approve(db, version_id, user_id=user.user_id, roles=user.roles,
                          comment=body.comment, firm_id=user.firm_id)
    except svc.RuleError as exc:
        raise _err(exc) from None
    return res.as_dict()


@router.post("/{version_id}/reject", response_model=RuleOut)
def reject_rule(version_id: str, body: RuleDecision, user: CurrentUser,
                db: DbSession) -> RuleOut:
    try:
        row = svc.reject(db, version_id, user_id=user.user_id, roles=user.roles,
                         comment=body.comment, firm_id=user.firm_id)
    except svc.RuleError as exc:
        raise _err(exc) from None
    return RuleOut.model_validate(svc.rule_dict(svc._from_row(row)))
