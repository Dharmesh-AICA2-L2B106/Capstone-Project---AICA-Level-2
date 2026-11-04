"""Per-firm review and approval of the shared default rules (D42-D45).

The seed rules are *defaults*: best-practice values loaded once for the whole deployment with
status ``pending_verification`` (D24). Each audit firm's partners review them inside the tool:

* **approve** a default for the firm - a ``firm_rule_approvals`` row (firm, version). The shared
  row is not edited, so another firm still sees it as pending until *its* partner approves;
* **override** - propose a firm-level (or engagement-level) version with the firm's own value,
  which the firm's partner then approves (the normal close / supersede / STALE workflow,
  limited to the firm's or engagement's own results);
* **reject** a firm proposal.

Approval rights follow the rule domain (:func:`app.services.rules.firm_approver_roles`): tax
rules need the firm's Tax Partner, methodology rules its Partner. Every decision is written to
``audit_log``. No AI is involved and no value is calculated here: partners enter values and
cite the source; the engines only read the resolved version.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Client, EngagementMember, Firm, FirmRuleApproval, RuleVersion
from app.services import rules as R
from app.services.rules import Rule, RuleError, RuleScope

FIRM_ADMIN_ROLES = ("Partner", "TaxPartner", "Admin")  # firm settings
PLATFORM_ROLES = ("Admin",)  # register firms / link clients (no firm claim)
REVIEW_STATUSES = ("approved_by_firm", "overridden", "awaiting_firm_approval", "not_effective")


# --------------------------------------------------------------------------- firms
def firm_dict(f: Firm) -> dict[str, Any]:
    return {"id": f.id, "name": f.name, "require_approved_rules": bool(f.require_approved_rules),
            "rules_allow_pending": get_settings().rules_allow_pending,
            "pending_rules_resolve": get_settings().rules_allow_pending
            and not f.require_approved_rules}


def get_firm(s: Session, firm_id: str | None) -> Firm:
    if firm_id is None:
        raise RuleError("Your sign-in is not linked to a firm (no firm claim in the token)", 403)
    firm = s.get(Firm, firm_id)
    if firm is None:
        raise RuleError("Your firm is not registered in AuditSmart yet; ask the platform "
                        "administrator to register it", 403)
    return firm


def create_firm(s: Session, *, firm_id: str, name: str, user_id: str,
                require_approved_rules: bool = False) -> Firm:
    if s.get(Firm, firm_id) is not None:
        raise RuleError(f"Firm '{firm_id}' already exists", 409)
    firm = Firm(id=firm_id, name=name, require_approved_rules=require_approved_rules,
                created_by=user_id)
    s.add(firm)
    s.flush()
    R._audit(s, user_id, "firm_create", "firm", firm.id, None, firm_dict(firm))
    s.commit()
    return firm


def assign_client(s: Session, *, firm_id: str, client_id: str, user_id: str) -> Client:
    """Link an unassigned (legacy) client to a firm. Moving a client between firms is refused."""
    if s.get(Firm, firm_id) is None:
        raise RuleError("Firm not found", 404)
    client = s.get(Client, client_id)
    if client is None:
        raise RuleError("Client not found", 404)
    if client.firm_id == firm_id:
        return client
    if client.firm_id is not None:
        raise RuleError("The client already belongs to another firm; moving clients between "
                        "firms is not supported", 409)
    client.firm_id = firm_id
    R._audit(s, user_id, "client_firm", "client", client.id, {"firm_id": None},
             {"firm_id": firm_id})
    s.commit()
    return client


def update_settings(s: Session, firm: Firm, *, require_approved_rules: bool, user_id: str,
                    roles: Iterable[str], comment: str | None) -> Firm:
    if not set(roles).intersection(FIRM_ADMIN_ROLES):
        raise RuleError("Only a Partner, Tax Partner or Admin of the firm can change its "
                        "settings", 403)
    text = R.check_comment(comment)
    old = firm_dict(firm)
    firm.require_approved_rules = require_approved_rules
    R._audit(s, user_id, "firm_settings", "firm", firm.id, old,
             {**firm_dict(firm), "comment": text})
    s.commit()
    R.invalidate()
    return firm


def check_engagement(s: Session, firm_id: str, engagement_id: str, user_id: str) -> None:
    """The engagement must be one of the firm's and the user a member of it."""
    if R.firm_of_engagement(s, engagement_id) != firm_id:
        raise RuleError("Engagement not found", 404)  # never reveal another firm's engagement
    member = s.scalars(select(EngagementMember).where(
        EngagementMember.engagement_id == engagement_id,
        EngagementMember.user_id == user_id)).first()
    if member is None:
        raise RuleError("You are not a member of this engagement", 403)


# --------------------------------------------------------------------------- review
def _default_version(rule_key: str, on: date) -> Rule | None:
    """The shared default covering ``on`` (approved before pending), ignoring firm sign-off."""
    try:
        return R.resolve(rule_key, on, R.default_rules(), allow_pending=True, scope=R.NO_SCOPE)
    except (R.RuleNotFound, R.RuleConflict):
        return None


def _approval(s: Session, firm_id: str, version_id: str | None) -> FirmRuleApproval | None:
    if version_id is None:
        return None
    return s.scalars(select(FirmRuleApproval).where(
        FirmRuleApproval.firm_id == firm_id,
        FirmRuleApproval.rule_version_id == version_id)).first()


def _covering(rows: Iterable[Rule], on: date, status: str = "approved") -> Rule | None:
    hits = [r for r in rows if r.status == status and r.covers(on)]
    return hits[0] if len(hits) == 1 else None


def review(s: Session, firm: Firm, *, on: date | None = None, domain: str | None = None,
           status: str | None = None, engagement_id: str | None = None) -> dict[str, Any]:
    """Every default rule with the firm's position on it, in one list."""
    when = on or date.today()
    pool = R.all_rules()
    keys = sorted({r.rule_key for r in pool if r.firm_id is None})
    if domain:
        keys = [k for k in keys if R.domain_of(k) == domain.upper()]
    scope = RuleScope(firm_id=firm.id, engagement_id=engagement_id,
                      require_approved=bool(firm.require_approved_rules))
    items: list[dict[str, Any]] = []
    for key in keys:
        mine = [r for r in pool if r.rule_key == key and r.firm_id == firm.id]
        firm_level = [r for r in mine if r.engagement_id is None]
        eng_level = [r for r in mine if engagement_id and r.engagement_id == engagement_id]
        default = _default_version(key, when)
        appr = _approval(s, firm.id, default.id if default else None)
        firm_override = _covering(firm_level, when)
        eng_override = _covering(eng_level, when)
        try:
            effective: dict[str, Any] | None = R.rule_dict(R.resolve(key, when, pool,
                                                                     scope=scope))
            effective_error = None
        except (R.RuleNotFound, R.RuleConflict) as exc:
            effective, effective_error = None, str(exc)
        if eng_override or firm_override:
            state = "overridden"
        elif appr is not None:
            state = "approved_by_firm"
        elif default is not None:
            state = "awaiting_firm_approval"
        else:
            state = "not_effective"
        if status and state != status:
            continue
        items.append({
            "rule_key": key, "domain": R.domain_of(key),
            "unit": default.unit if default else "",
            "review_status": state,
            "default": R.rule_dict(default) if default else None,
            "firm_approval": None if appr is None else {
                "approved_by": appr.approved_by, "approved_at": appr.approved_at.isoformat(),
                "comment": appr.comment},
            "firm_override": R.rule_dict(firm_override) if firm_override else None,
            "engagement_override": R.rule_dict(eng_override) if eng_override else None,
            "open_proposals": [R.rule_dict(r) for r in mine if r.status == "proposed"],
            "effective": effective, "effective_error": effective_error,
            "approver_roles": list(R.firm_approver_roles(key)),
        })
    summary = {k: sum(1 for i in items if i["review_status"] == k) for k in REVIEW_STATUSES}
    return {"firm": firm_dict(firm), "on": when.isoformat(), "engagement_id": engagement_id,
            "summary": {**summary, "total": len(items),
                        "open_proposals": sum(len(i["open_proposals"]) for i in items)},
            "items": items}


# --------------------------------------------------------------------------- decisions
def approve(s: Session, firm: Firm, rule_key: str, *, user_id: str, roles: Iterable[str],
            comment: str | None, version_id: str | None = None,
            on: date | None = None) -> dict[str, Any]:
    """Approve the default covering ``on`` for the firm, or one of the firm's proposals."""
    if version_id is not None:
        row = s.get(RuleVersion, version_id)
        if row is None or row.rule_key != rule_key or row.firm_id not in (None, firm.id):
            raise RuleError("Rule version not found", 404)
        if row.firm_id == firm.id:  # the firm's own override proposal
            if row.engagement_id is not None:
                check_engagement(s, firm.id, row.engagement_id, user_id)
            res = R.approve(s, row.id, user_id=user_id, roles=roles, comment=comment,
                            firm_id=firm.id)
            return {"action": "override_approved", **res.as_dict()}
        default: Rule | None = R._from_row(row)
    else:
        default = _default_version(rule_key, on or date.today())
    if default is None:
        raise RuleError(f"No default version of '{rule_key}' is effective on "
                        f"{on or date.today()}", 404)
    text = R.check_firm_approver(rule_key, roles, comment)
    if default.status not in ("approved", "pending_verification"):
        raise RuleError(f"{default.ref} is {default.status}; only a current default can be "
                        "approved for the firm", 409)
    if _approval(s, firm.id, default.id) is not None:
        raise RuleError(f"{default.ref} is already approved for your firm", 409)
    appr = FirmRuleApproval(firm_id=firm.id, rule_version_id=default.id, rule_key=rule_key,
                            approved_by=user_id, approved_at=datetime.now(UTC), comment=text)
    s.add(appr)
    try:
        s.flush()
    except IntegrityError:  # pragma: no cover - concurrent double approval
        s.rollback()
        raise RuleError(f"{default.ref} is already approved for your firm", 409) from None
    R._audit(s, user_id, "firm_rule_approve", "rule_version", default.id, None,
             {"firm_id": firm.id, "ref": default.ref, "value": default.value,
              "comment": text})
    s.commit()
    R.invalidate()
    # The value is unchanged, so no result becomes STALE.
    return {"action": "default_approved", "firm_id": firm.id, "approved_by": user_id,
            "approved_at": appr.approved_at.isoformat(),
            "rule": R.rule_dict(replace(default, status="approved", firm_approved=True)),
            "closed": [], "superseded": [], "stale": []}


def propose_override(s: Session, firm: Firm, rule_key: str, *, user_id: str,
                     roles: Iterable[str], value: Any, effective_from: date,
                     effective_to: date | None, comment: str | None,
                     engagement_id: str | None = None, source_url: str | None = None,
                     source_ref: str = "", unit: str = "") -> RuleVersion:
    """A firm (or engagement) version of a default rule, status ``proposed``."""
    if not set(roles).intersection(R.FIRM_PROPOSER_ROLES):
        raise RuleError("Only a Manager, Partner or Tax Partner of the firm can propose a "
                        "rule change", 403)
    text = R.check_comment(comment)
    defaults = [r for r in R.default_rules() if r.rule_key == rule_key]
    if not defaults:
        raise RuleError(f"Rule '{rule_key}' is not in the Rules Library", 404)
    if engagement_id is not None:
        check_engagement(s, firm.id, engagement_id, user_id)
    base = _default_version(rule_key, effective_from)
    row = R.propose(s, rule_key=rule_key, value=value, effective_from=effective_from,
                    effective_to=effective_to, source_url=source_url, source_ref=source_ref,
                    unit=unit or (base.unit if base else defaults[0].unit),
                    proposed_by=user_id, comment=text, firm_id=firm.id,
                    engagement_id=engagement_id, based_on_id=base.id if base else None)
    R._audit(s, user_id, "firm_rule_override", "rule_version", row.id, None,
             {**R._snapshot(row), "based_on": base.ref if base else None})
    s.commit()
    return row


def reject(s: Session, firm: Firm, rule_key: str, *, version_id: str, user_id: str,
           roles: Iterable[str], comment: str | None) -> RuleVersion:
    row = s.get(RuleVersion, version_id)
    if row is None or row.rule_key != rule_key or row.firm_id != firm.id:
        raise RuleError("Rule version not found", 404)
    return R.reject(s, row.id, user_id=user_id, roles=roles, comment=comment, firm_id=firm.id)

