"""Partner-facing rule review for each audit firm (D42, docs/MULTI_FIRM_APPROVAL.md).

Firm users (token carries the firm claim):
GET   /v1/firm                              -> the caller's firm and its rule settings
PATCH /v1/firm/settings                     -> require_approved_rules (Partner/TaxPartner/Admin)
GET   /v1/firm/rules/review?on=&domain=&status=&engagement_id=
                                            -> every default rule with the firm's position
POST  /v1/firm/rules/{rule_key}/approve     -> approve the default (or the firm's proposal)
                                               for the firm: TaxPartner (tax) / Partner
                                               (methodology), mandatory comment
POST  /v1/firm/rules/{rule_key}/override    -> propose a firm or engagement value
                                               (Manager/Partner/TaxPartner), mandatory comment
POST  /v1/firm/rules/{rule_key}/reject      -> reject one of the firm's proposals

Platform administrators (Admin role, no firm claim):
POST  /v1/firms                             -> register a firm
PUT   /v1/firms/{firm_id}/clients/{client_id} -> link an unassigned client to a firm
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query

from app.api.v1.deps import CurrentUser, DbSession
from app.models import Firm
from app.schemas.firm_rules import (
    FirmCreate,
    FirmRuleApprove,
    FirmRuleOverride,
    FirmRuleReject,
    FirmSettings,
)
from app.schemas.rules import RuleOut
from app.services import firm_rules as svc
from app.services import rules as R

router = APIRouter(tags=["firm-rules"])


def _err(exc: R.RuleError) -> HTTPException:
    return HTTPException(exc.status_code, exc.message)


def _firm(user: CurrentUser, db: DbSession) -> Firm:
    try:
        return svc.get_firm(db, user.firm_id)
    except R.RuleError as exc:
        raise _err(exc) from None


def _platform_admin(user: CurrentUser) -> None:
    if user.firm_id is not None or not set(user.roles).intersection(svc.PLATFORM_ROLES):
        raise HTTPException(403, "Only a platform Admin (no firm claim) can manage firms")


@router.get("/firm", summary="Your firm and its rule settings")
def my_firm(user: CurrentUser, db: DbSession) -> dict[str, Any]:
    return svc.firm_dict(_firm(user, db))


@router.patch("/firm/settings", summary="Tighten or relax the firm's pending-rule setting")
def firm_settings(body: FirmSettings, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    firm = _firm(user, db)
    try:
        svc.update_settings(db, firm, require_approved_rules=body.require_approved_rules,
                            user_id=user.user_id, roles=user.roles, comment=body.comment)
    except R.RuleError as exc:
        raise _err(exc) from None
    return svc.firm_dict(firm)


@router.get("/firm/rules/review", summary="Review every default rule for your firm")
def review_rules(user: CurrentUser, db: DbSession,
                 on: Annotated[date | None, Query()] = None,
                 domain: Annotated[str | None, Query(max_length=32)] = None,
                 status: Annotated[str | None, Query(
                     pattern="^(" + "|".join(svc.REVIEW_STATUSES) + ")$")] = None,
                 engagement_id: Annotated[str | None, Query(max_length=36)] = None,
                 ) -> dict[str, Any]:
    firm = _firm(user, db)
    try:
        if engagement_id is not None:
            svc.check_engagement(db, firm.id, engagement_id, user.user_id)
        return svc.review(db, firm, on=on, domain=domain, status=status,
                          engagement_id=engagement_id)
    except R.RuleError as exc:
        raise _err(exc) from None


@router.post("/firm/rules/{rule_key}/approve",
             summary="Approve a default (or your firm's proposal) for your firm")
def approve_rule(rule_key: str, body: FirmRuleApprove, user: CurrentUser,
                 db: DbSession) -> dict[str, Any]:
    firm = _firm(user, db)
    try:
        return svc.approve(db, firm, rule_key, user_id=user.user_id, roles=user.roles,
                           comment=body.comment, version_id=body.version_id, on=body.on)
    except R.RuleError as exc:
        raise _err(exc) from None


@router.post("/firm/rules/{rule_key}/override", status_code=201, response_model=RuleOut,
             summary="Propose your firm's (or one engagement's) value for a rule")
def override_rule(rule_key: str, body: FirmRuleOverride, user: CurrentUser,
                  db: DbSession) -> RuleOut:
    firm = _firm(user, db)
    try:
        row = svc.propose_override(
            db, firm, rule_key, user_id=user.user_id, roles=user.roles, value=body.value,
            effective_from=body.effective_from, effective_to=body.effective_to,
            comment=body.comment, engagement_id=body.engagement_id,
            source_url=body.source_url, source_ref=body.source_ref, unit=body.unit)
    except R.RuleError as exc:
        raise _err(exc) from None
    return RuleOut.model_validate(R.rule_dict(R._from_row(row)))


@router.post("/firm/rules/{rule_key}/reject", response_model=RuleOut,
             summary="Reject one of your firm's rule proposals")
def reject_rule(rule_key: str, body: FirmRuleReject, user: CurrentUser,
                db: DbSession) -> RuleOut:
    firm = _firm(user, db)
    try:
        row = svc.reject(db, firm, rule_key, version_id=body.version_id,
                         user_id=user.user_id, roles=user.roles, comment=body.comment)
    except R.RuleError as exc:
        raise _err(exc) from None
    return RuleOut.model_validate(R.rule_dict(R._from_row(row)))


@router.post("/firms", status_code=201, summary="Register a firm (platform Admin)")
def create_firm(body: FirmCreate, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    _platform_admin(user)
    try:
        firm = svc.create_firm(db, firm_id=body.id, name=body.name, user_id=user.user_id,
                               require_approved_rules=body.require_approved_rules)
    except R.RuleError as exc:
        raise _err(exc) from None
    return svc.firm_dict(firm)


@router.put("/firms/{firm_id}/clients/{client_id}",
            summary="Link an unassigned client to a firm (platform Admin)")
def assign_client(firm_id: str, client_id: str, user: CurrentUser,
                  db: DbSession) -> dict[str, str]:
    _platform_admin(user)
    try:
        client = svc.assign_client(db, firm_id=firm_id, client_id=client_id,
                                   user_id=user.user_id)
    except R.RuleError as exc:
        raise _err(exc) from None
    return {"client_id": client.id, "firm_id": str(client.firm_id)}
