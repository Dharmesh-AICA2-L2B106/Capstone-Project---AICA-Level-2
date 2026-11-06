"""Engagement sync from the front end (Stage 5.2, D50-D55).

Lovable keeps clients, engagements and teams in its own database. The engine needs the same
rows because every engagement-scoped call checks membership and the firm boundary
(``check_membership``, D42/D45). ``PUT /v1/engagements/{id}`` upserts them idempotently.

Rules (docs/MULTI_FIRM_APPROVAL.md section 10):
* The firm always comes from the caller's token; it must be registered (``POST /v1/firms``).
* Another firm's client -> 404 (never revealed); another firm's engagement -> 403.
* A client that is not linked to any firm (legacy) -> 409: the platform Admin links it first.
* Create: Manager, Partner, TaxPartner or Admin of the firm. Update: a team member whose
  engagement role is Manager, Partner or TaxPartner, or an Admin of the firm.
* ``members`` replaces the whole team. Every change is written to ``audit_log`` (old/new).
* A changed year end marks the engagement's current results STALE (the rule date and the
  period depend on it); a changed emirate re-checks JE runs against the calendar.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Client, Engagement, EngagementMember, Firm, InputVatRun, JeRun, Sample
from app.schemas.engagements import EngagementSync
from app.services import calendar_admin
from app.services.rules import _audit, firm_of_engagement

SYNC_ROLES = ("Manager", "Partner", "TaxPartner", "Admin")  # app roles that may sync
TEAM_EDITORS = ("Manager", "Partner", "TaxPartner")  # engagement roles that may update
FIRM_ADMIN = "Admin"
EMIRATE_CODES = {"AUH": "Abu Dhabi", "AD": "Abu Dhabi", "DXB": "Dubai", "SHJ": "Sharjah",
                 "AJM": "Ajman", "UAQ": "Umm Al Quwain", "RAK": "Ras Al Khaimah",
                 "FUJ": "Fujairah"}
ENGAGEMENT_FIELDS = ("framework", "materiality", "perf_materiality", "trivial", "status")


class EngagementError(ValueError):
    def __init__(self, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def canonical_emirate(name: str) -> str:
    raw = name.strip()
    if raw.upper() in EMIRATE_CODES:
        return EMIRATE_CODES[raw.upper()]
    for e in calendar_admin.EMIRATES:
        if e.lower() == raw.lower():
            return e
    raise EngagementError(f"Unknown emirate '{name}' (use one of "
                          f"{', '.join(calendar_admin.EMIRATES)}).")


def _money(v: Decimal | None) -> str | None:
    return None if v is None else str(Decimal(v).quantize(Decimal("0.01")))


def client_dict(c: Client) -> dict[str, Any]:
    return {"id": c.id, "client_code": c.client_code, "name": c.name, "emirate": c.emirate,
            "entity_type": c.entity_type, "firm_id": c.firm_id}


def engagement_dict(e: Engagement) -> dict[str, Any]:
    return {"id": e.id, "client_id": e.client_id, "fye": e.fye.isoformat(),
            "framework": e.framework, "materiality": _money(e.materiality),
            "perf_materiality": _money(e.perf_materiality), "trivial": _money(e.trivial),
            "status": e.status}


def members_of(s: Session, engagement_id: str) -> list[dict[str, str]]:
    rows = s.scalars(select(EngagementMember).where(
        EngagementMember.engagement_id == engagement_id)
        .order_by(EngagementMember.user_id)).all()
    return [{"user_id": m.user_id, "role": m.role} for m in rows]


def view(s: Session, e: Engagement) -> dict[str, Any]:
    c = s.get(Client, e.client_id)
    assert c is not None  # FK
    return {"engagement": engagement_dict(e), "client": client_dict(c),
            "members": members_of(s, e.id)}


def _member_role(s: Session, engagement_id: str, user_id: str) -> str | None:
    m = s.get(EngagementMember, {"engagement_id": engagement_id, "user_id": user_id})
    return m.role if m is not None else None


def check_access(s: Session, firm_id: str | None, engagement_id: str, user_id: str,
                 roles: Iterable[str], *, edit: bool) -> Engagement:
    """The engagement exists, is the caller's firm's, and the caller may read / edit it."""
    eng = s.get(Engagement, engagement_id)
    if eng is None:
        raise EngagementError("Engagement not found", 404)
    owner = firm_of_engagement(s, engagement_id)
    if owner is None:
        raise EngagementError("This engagement's client is not linked to a firm yet; ask the "
                              "platform administrator to link it (PUT /v1/firms/{firm_id}/"
                              "clients/{client_id})", 409)
    if owner != firm_id:
        raise EngagementError("This engagement belongs to another firm.", 403)
    role = _member_role(s, engagement_id, user_id)
    if FIRM_ADMIN in set(roles):
        return eng
    if role is None:
        raise EngagementError("You are not a member of this engagement.", 403)
    if edit and role not in TEAM_EDITORS:
        raise EngagementError(f"Your engagement role ({role}) cannot change this engagement; "
                              f"needs {', '.join(TEAM_EDITORS)} or a firm Admin.", 403)
    return eng


def _stale_all(s: Session, engagement_id: str, user_id: str, reason: str
               ) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    groups: list[tuple[str, Sequence[Sample | JeRun | InputVatRun]]] = [
        ("sample", s.scalars(select(Sample).where(
            Sample.engagement_id == engagement_id, Sample.status != "STALE")).all()),
        ("je_run", s.scalars(select(JeRun).where(
            JeRun.engagement_id == engagement_id, JeRun.status != "STALE")).all()),
        ("input_vat_run", s.scalars(select(InputVatRun).where(
            InputVatRun.engagement_id == engagement_id, InputVatRun.status != "STALE")).all()),
    ]
    for kind, rows in groups:
        for r in rows:
            r.status = "STALE"
            out.append({"kind": kind, "id": r.id, "engagement_id": engagement_id})
            _audit(s, user_id, "stale", kind, r.id, {"status": "current"},
                   {"status": "STALE", "reason": reason})
    return out


def _sync_client(s: Session, firm: Firm, body: EngagementSync, user_id: str
                 ) -> tuple[Client, bool]:
    """Create or update the client in the caller's firm. Returns (client, emirate_changed)."""
    data = body.client
    emirate = canonical_emirate(data.emirate)
    code = data.client_code.strip()
    clash = s.scalars(select(Client).where(Client.firm_id == firm.id,
                                           Client.client_code == code,
                                           Client.id != data.id)).first()
    if clash is not None:
        raise EngagementError(f"Client code '{code}' is already used by another client of "
                              "your firm", 409)
    c = s.get(Client, data.id)
    new = {"client_code": code, "name": data.name.strip(), "emirate": emirate,
           "entity_type": data.entity_type}
    if c is None:
        c = Client(id=data.id, firm_id=firm.id, **new)
        s.add(c)
        s.flush()
        _audit(s, user_id, "client_sync_create", "client", c.id, None, client_dict(c))
        return c, False
    if c.firm_id is None:
        raise EngagementError("This client is not linked to a firm yet; ask the platform "
                              "administrator to link it (PUT /v1/firms/{firm_id}/clients/"
                              "{client_id})", 409)
    if c.firm_id != firm.id:
        raise EngagementError("Client not found", 404)  # never reveal another firm's client
    old = client_dict(c)
    for k, v in new.items():
        setattr(c, k, v)
    if client_dict(c) != old:
        _audit(s, user_id, "client_sync_update", "client", c.id, old, client_dict(c))
    return c, old["emirate"] != emirate


def upsert(s: Session, firm: Firm, engagement_id: str, body: EngagementSync, *,
           user_id: str, roles: Iterable[str]) -> dict[str, Any]:
    roles = frozenset(roles)
    if not roles.intersection(SYNC_ROLES):
        raise EngagementError("Syncing an engagement needs one of these roles: "
                              f"{', '.join(SYNC_ROLES)}.", 403)
    eng = s.get(Engagement, engagement_id)
    created = eng is None
    if eng is not None:
        check_access(s, firm.id, engagement_id, user_id, roles, edit=True)
        if eng.client_id != body.client.id:
            raise EngagementError("An engagement cannot move to another client", 409)
    client, emirate_changed = _sync_client(s, firm, body, user_id)
    sent = body.model_fields_set
    if eng is None:
        eng = Engagement(id=engagement_id, client_id=client.id, fye=body.fye,
                         **{k: getattr(body, k) for k in ENGAGEMENT_FIELDS
                            if k != "status"},
                         status=(body.status or "planning").strip().lower())
        s.add(eng)
        s.flush()
        old_eng: dict[str, Any] | None = None
    else:
        old_eng = engagement_dict(eng)
        eng.fye = body.fye
        for k in ENGAGEMENT_FIELDS:
            if k in sent:
                v = getattr(body, k)
                if k == "status":
                    v = (v or "planning").strip().lower()
                setattr(eng, k, v)
        s.flush()
    new_eng = engagement_dict(eng)
    old_members = members_of(s, eng.id)
    wanted = {m.user_id: m.role for m in body.members}
    for row in s.scalars(select(EngagementMember).where(
            EngagementMember.engagement_id == eng.id)).all():
        if row.user_id not in wanted:
            s.delete(row)
        elif row.role != wanted[row.user_id]:
            row.role = wanted[row.user_id]
    have = {m["user_id"] for m in old_members}
    s.add_all([EngagementMember(engagement_id=eng.id, user_id=u, role=r)
               for u, r in wanted.items() if u not in have])
    s.flush()
    new_members = members_of(s, eng.id)
    if old_eng != new_eng or old_members != new_members:
        _audit(s, user_id, "engagement_sync_create" if created else "engagement_sync_update",
               "engagement", eng.id,
               None if old_eng is None else {**old_eng, "members": old_members},
               {**new_eng, "members": new_members, "firm_id": firm.id})
    stale: list[dict[str, Any]] = []
    if old_eng is not None and old_eng["fye"] != new_eng["fye"]:
        stale += _stale_all(s, eng.id, user_id,
                            f"year end changed {old_eng['fye']} -> {new_eng['fye']}")
    if emirate_changed:
        seen = {x["id"] for x in stale}
        stale += [x for x in calendar_admin.mark_stale(
            s, client_ids=[client.id], user_id=user_id, reason="client emirate changed")
            if x["id"] not in seen]
    s.commit()
    return {"created": created, **view(s, eng), "stale": stale}
