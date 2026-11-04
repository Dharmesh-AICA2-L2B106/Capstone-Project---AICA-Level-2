"""Rules Library (SPEC 3.4, prompt 3.8).

Every tax/methodology parameter the engine uses is a *versioned rule* with an effective period.
Calculations call :func:`get_rule` (``rule_key``, ``on_date``) and record the ``rule_key@vN`` they
used, so a result can be reproduced and marked STALE when a rule it relied on is superseded.

Backing store
* ``rule_versions`` table (Appendix A), seeded idempotently from ``seed_data/rules_seed.json``
  by :func:`seed_database`; enabled by the app lifespan (and the test fixture) via
  :func:`use_database`.
* Without a database (pure unit tests, CLI) the seed file itself is the registry.

Resolution - exactly one version (prompt 3.8)
* candidates: versions whose [effective_from, effective_to] covers ``on_date`` and whose status is
  ``approved`` - or, while ``RULES_ALLOW_PENDING`` is true, ``pending_verification`` (DECISIONS
  D24: every seed rule is still awaiting Tax Partner sign-off).
* an approved version always wins over a pending one; two versions of the same status
  -> RuleConflict; none -> RuleNotFound with a clear message.

Workflow: :func:`propose` -> :func:`approve` / :func:`reject` (mandatory comment; Tax Partner for
tax domains, Partner for methodology domains, Admin never - D43, D47).
Approval closes the prior version, never edits an approved row (immutability guard), writes
``audit_log`` and marks dependent results STALE.

Multi-firm layers (D42, docs/MULTI_FIRM_APPROVAL.md)
* ``firm_id IS NULL`` rows are the shared *defaults* (seed, pending_verification).
* A firm partner approves a default *for the firm* (``firm_rule_approvals``; the shared row is
  never edited) or approves a firm override (``firm_id`` set) or an engagement override
  (``firm_id`` + ``engagement_id``). Workflow helpers live in ``app.services.firm_rules``.
* Calculations resolve inside a :class:`RuleScope` (context variable set per request / job from
  the engagement): engagement override > firm override > default (approved for the firm, else
  pending while allowed). Without a firm the original single-library behaviour is unchanged.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Collection, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    AuditLog,
    Client,
    Dataset,
    Engagement,
    Firm,
    FirmRuleApproval,
    InputVatRun,
    JeRun,
    RuleVersion,
    Sample,
)

SEED_PATH = Path(__file__).resolve().parents[2] / "seed_data" / "rules_seed.json"

IMPLEMENTED_BY_PROMPT = "3.8"

# D47: shared defaults follow the same domain split as firm decisions (D43); Admin never approves.
APPROVER_ROLES = ("TaxPartner", "Partner")
PROPOSER_ROLES = ("TaxPartner", "Admin", "Partner", "Manager")
MIN_COMMENT = 10
RESOLVABLE = ("approved", "pending_verification")
OPEN_STATUSES = ("proposed", "pending_verification")
CACHE_TTL_SECONDS = 30.0
KEY_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[A-Za-z0-9_]+)+$")
REF_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[A-Za-z0-9_]+)+@v\d+$")
DOMAINS = {
    "vat": "VAT", "input_vat": "INPUT_VAT", "ct": "CT", "trn": "TRN", "sampling": "SAMPLING",
    "benford": "BENFORD", "legal_ref": "LEGAL_REF", "validation": "VALIDATION", "je": "JE",
}
FAR_FUTURE = date(9999, 12, 31)


class RuleNotFound(KeyError):
    """No resolvable version of a rule covers the date."""

    def __str__(self) -> str:
        return str(self.args[0]) if self.args else "rule not found"


class RuleConflict(RuntimeError):
    """More than one version of the same status covers the date (data integrity problem)."""


class RuleError(ValueError):
    def __init__(self, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class ImmutableRuleError(RuntimeError):
    """An approved rule version may only be closed (effective_to) or superseded."""


def domain_of(rule_key: str) -> str:
    return DOMAINS.get(rule_key.split(".", 1)[0], "OTHER")


@dataclass(frozen=True)
class Rule:
    rule_key: str
    version: int
    effective_from: date
    value: Any
    status: str
    source_ref: str
    unit: str = ""
    effective_to: date | None = None
    source_url: str | None = None
    id: str | None = None
    firm_id: str | None = None  # D42: None = shared default
    engagement_id: str | None = None
    firm_approved: bool = False  # a default approved by the resolving firm's partner

    @property
    def layer(self) -> str:
        if self.firm_id is None:
            return "default"
        return "engagement" if self.engagement_id else "firm"

    @property
    def ref(self) -> str:
        return f"{self.rule_key}@v{self.version}"

    @property
    def domain(self) -> str:
        return domain_of(self.rule_key)

    def covers(self, when: date) -> bool:
        return self.effective_from <= when and (self.effective_to is None
                                                or when <= self.effective_to)


def _d(v: Any) -> date | None:
    return date.fromisoformat(str(v)) if v else None


def _parse(item: Mapping[str, Any]) -> Rule:
    return Rule(
        rule_key=str(item["rule_key"]),
        version=int(item["version"]),
        effective_from=date.fromisoformat(str(item["effective_from"])),
        effective_to=_d(item.get("effective_to")),
        value=item["value"],
        status=str(item["status"]),
        source_ref=str(item.get("source_ref", "")),
        unit=str(item.get("unit", "")),
        source_url=item.get("source_url") or None,
    )


@lru_cache
def load_rules(path: str = str(SEED_PATH)) -> tuple[Rule, ...]:
    """The seed file (registry when no database is enabled)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return tuple(_parse(r) for r in data["rules"])


def _from_row(row: RuleVersion) -> Rule:
    return Rule(rule_key=row.rule_key, version=int(row.version or 1),
                effective_from=row.effective_from, effective_to=row.effective_to,
                value=row.value, status=row.status, source_ref=row.source_ref or "",
                unit=row.unit or "", source_url=row.source_url, id=row.id,
                firm_id=row.firm_id, engagement_id=row.engagement_id)


# --------------------------------------------------------------------------- registry
@dataclass
class _State:
    db: bool = False
    cache: tuple[Rule, ...] | None = None
    adopted: frozenset[tuple[str, str]] = frozenset()  # (firm_id, rule_version_id)
    loaded_at: float = 0.0


_state = _State()


def use_database(enabled: bool = True) -> None:
    """Resolve rules from ``rule_versions`` (True) or the seed file (False)."""
    _state.db = enabled
    invalidate()


def invalidate() -> None:
    _state.cache = None


def _session() -> Session:
    from app.core.db import session_factory

    return session_factory()()


def all_rules() -> tuple[Rule, ...]:
    """Every version (defaults and all firms' overrides); resolution filters by scope."""
    if not _state.db:
        return load_rules()
    if _state.cache is not None and time.monotonic() - _state.loaded_at < CACHE_TTL_SECONDS:
        return _state.cache
    with _session() as s:
        rows = tuple(_from_row(r) for r in s.scalars(select(RuleVersion)).all())
        adopted = frozenset((a.firm_id, a.rule_version_id)
                            for a in s.scalars(select(FirmRuleApproval)).all())
    _state.cache, _state.adopted, _state.loaded_at = rows, adopted, time.monotonic()
    return rows


def default_rules() -> tuple[Rule, ...]:
    """The shared defaults only (no firm overrides) - what platform users and the monitor see."""
    return tuple(r for r in all_rules() if r.firm_id is None)


def firm_adoptions() -> frozenset[tuple[str, str]]:
    """(firm_id, rule_version_id) pairs: defaults a firm partner approved for the firm."""
    if not _state.db:
        return frozenset()
    all_rules()  # refresh the cache together with the versions
    return _state.adopted


# --------------------------------------------------------------------------- scope (D42)
@dataclass(frozen=True)
class RuleScope:
    """Who a resolution is for. Empty = platform / single-firm (shared defaults only)."""

    firm_id: str | None = None
    engagement_id: str | None = None
    require_approved: bool = False  # firms.require_approved_rules (tighten-only, D44)


NO_SCOPE = RuleScope()
_scope: ContextVar[RuleScope | None] = ContextVar("auditsmart_rule_scope", default=None)


def current_scope() -> RuleScope:
    return _scope.get() or NO_SCOPE


@contextmanager
def rule_scope(scope: RuleScope) -> Iterator[RuleScope]:
    token = _scope.set(scope)
    try:
        yield scope
    finally:
        _scope.reset(token)


def firm_of_engagement(s: Session, engagement_id: str | None) -> str | None:
    if not engagement_id:
        return None
    eng = s.get(Engagement, engagement_id)
    client = s.get(Client, eng.client_id) if eng is not None else None
    return client.firm_id if client is not None else None


def scope_for_engagement(s: Session, engagement_id: str | None) -> RuleScope:
    firm_id = firm_of_engagement(s, engagement_id)
    if firm_id is None:
        return RuleScope()
    return replace(scope_for_firm(s, firm_id), engagement_id=engagement_id)


def scope_for_firm(s: Session, firm_id: str | None) -> RuleScope:
    if firm_id is None:
        return RuleScope()
    firm = s.get(Firm, firm_id)
    return RuleScope(firm_id=firm_id,
                     require_approved=bool(firm is not None and firm.require_approved_rules))


@contextmanager
def engagement_scope(engagement_id: str | None) -> Iterator[RuleScope]:
    """Resolve rules for ``engagement_id``'s firm (and engagement overrides) inside the block."""
    if engagement_id:
        with _session() as s:
            scope = scope_for_engagement(s, engagement_id)
    else:
        scope = RuleScope()
    with rule_scope(scope) as sc:
        yield sc


def _pick(rule_key: str, when: date, rows: Sequence[Rule], status: str) -> Rule | None:
    hits = [r for r in rows if r.status == status]
    if len(hits) > 1:
        raise RuleConflict(f"Rule '{rule_key}' has {len(hits)} {status} versions effective "
                           f"on {when}: {', '.join(r.ref for r in hits)}")
    return hits[0] if hits else None


def _resolve_firm(rule_key: str, when: date, versions: Sequence[Rule], scope: RuleScope,
                  pending_ok: bool, adopted: Collection[tuple[str, str]]) -> Rule:
    firm = scope.firm_id
    covering = [r for r in versions if r.covers(when)]
    layers: list[list[Rule]] = []
    if scope.engagement_id:
        layers.append([r for r in covering if r.firm_id == firm
                       and r.engagement_id == scope.engagement_id])
    layers.append([r for r in covering if r.firm_id == firm and r.engagement_id is None])
    for rows in layers:
        hit = _pick(rule_key, when, rows, "approved")
        if hit is not None:
            return hit
    defaults = [r for r in covering if r.firm_id is None]
    g = (_pick(rule_key, when, defaults, "approved")
         or _pick(rule_key, when, defaults, "pending_verification"))
    if g is not None:
        if (str(firm), str(g.id)) in adopted:
            return replace(g, status="approved", firm_approved=True)
        if pending_ok:  # a default not yet approved by this firm's partner
            return replace(g, status="pending_verification")
        raise RuleNotFound(f"No approved version of rule '{rule_key}' is effective on {when} "
                           f"for this firm; {g.ref} awaits approval by the firm's audit partner")
    if not any(r.firm_id is None or r.firm_id == firm for r in versions):
        raise RuleNotFound(f"Rule '{rule_key}' is not in the Rules Library")
    raise RuleNotFound(f"No approved version of rule '{rule_key}' is effective on {when}")


def resolve(rule_key: str, on_date: date | None = None,
            rules: Iterable[Rule] | None = None, *, allow_pending: bool | None = None,
            scope: RuleScope | None = None,
            adopted: Collection[tuple[str, str]] | None = None) -> Rule:
    """The single version of ``rule_key`` effective on ``on_date`` (default today).

    ``scope`` defaults to the current :class:`RuleScope`; firm layers apply only when it names
    a firm (D42). Other firms' versions are never candidates.
    """
    when = on_date or date.today()
    sc = current_scope() if scope is None else scope
    pending_ok = get_settings().rules_allow_pending if allow_pending is None else allow_pending
    pool = all_rules() if rules is None else tuple(rules)
    if sc.firm_id is not None:
        versions = [r for r in pool if r.rule_key == rule_key
                    and (r.firm_id is None or r.firm_id == sc.firm_id)]
        return _resolve_firm(rule_key, when, versions, sc,
                             pending_ok and not sc.require_approved,
                             firm_adoptions() if adopted is None else adopted)
    versions = [r for r in pool if r.rule_key == rule_key and r.firm_id is None]
    covering = [r for r in versions if r.covers(when)]
    for status in ("approved", "pending_verification"):
        if status == "pending_verification" and not pending_ok:
            break
        hits = [r for r in covering if r.status == status]
        if len(hits) > 1:
            raise RuleConflict(f"Rule '{rule_key}' has {len(hits)} {status} versions effective "
                               f"on {when}: {', '.join(r.ref for r in hits)}")
        if hits:
            return hits[0]
    if not versions:
        raise RuleNotFound(f"Rule '{rule_key}' is not in the Rules Library")
    pend = [r.ref for r in covering if r.status == "pending_verification"]
    if pend:
        raise RuleNotFound(f"No approved version of rule '{rule_key}' is effective on {when}; "
                           f"{', '.join(pend)} awaits Tax Partner approval")
    raise RuleNotFound(f"No approved version of rule '{rule_key}' is effective on {when}")


def get_rule(rule_key: str, on_date: date | None = None) -> Rule:
    """Exactly one resolvable version of ``rule_key`` effective on ``on_date``."""
    return resolve(rule_key, on_date)


def by_ref(ref: str) -> Rule | None:  # refs are unique across firms (global version numbers)
    return next((r for r in all_rules() if r.ref == ref), None)


# --------------------------------------------------------------------------- seeding
def seed_database(session: Session | None = None) -> int:
    """Insert seed versions missing from ``rule_versions`` (idempotent). Returns rows added."""
    own = session is None
    s = session or _session()
    try:
        have = {(k, v) for k, v in s.execute(select(RuleVersion.rule_key, RuleVersion.version)
                                             .where(RuleVersion.firm_id.is_(None)))}
        added = 0
        for r in load_rules():
            if (r.rule_key, r.version) in have:
                continue
            s.add(RuleVersion(rule_key=r.rule_key, version=r.version, value=r.value,
                              effective_from=r.effective_from, effective_to=r.effective_to,
                              status=r.status, source_ref=r.source_ref, source_url=r.source_url,
                              unit=r.unit, domain=r.domain, proposed_by="seed"))
            added += 1
        s.commit()
    finally:
        if own:
            s.close()
    invalidate()
    return added


# --------------------------------------------------------------------------- immutability
_FROZEN = ("rule_key", "value", "effective_from", "source_url", "source_doc_hash", "version",
           "unit", "source_ref", "domain", "approved_by", "approved_at", "proposed_by", "comment")


@event.listens_for(Session, "before_flush")
def _guard_approved(session: Session, _ctx: Any, _inst: Any) -> None:
    from sqlalchemy import inspect

    for obj in session.deleted:
        if isinstance(obj, RuleVersion) and inspect(obj).committed_state.get(
                "status", obj.status) == "approved":
            raise ImmutableRuleError(f"Approved rule version {obj.rule_key}@v{obj.version} "
                                     "cannot be deleted")
    for obj in session.dirty:
        if not isinstance(obj, RuleVersion):
            continue
        state = inspect(obj)
        hist = state.attrs.status.history
        before = hist.deleted[0] if hist.deleted else obj.status
        if before != "approved":
            continue
        changed = [a for a in _FROZEN if state.attrs[a].history.has_changes()]
        if changed:
            raise ImmutableRuleError(f"Approved rule version {obj.rule_key}@v{obj.version} is "
                                     f"immutable (attempted change: {', '.join(changed)})")
        if obj.status not in ("approved", "superseded"):
            raise ImmutableRuleError("An approved rule version can only become superseded")
        to_hist = state.attrs.effective_to.history
        if to_hist.has_changes():
            old_to = to_hist.deleted[0] if to_hist.deleted else None
            new_to = obj.effective_to
            if new_to is None or (old_to is not None and new_to > old_to) \
                    or new_to < obj.effective_from - timedelta(days=1):
                raise ImmutableRuleError(f"Approved rule version {obj.rule_key}@v{obj.version} "
                                         "can only be closed earlier, never reopened")


# --------------------------------------------------------------------------- workflow
def _overlaps(a_from: date, a_to: date | None, b_from: date, b_to: date | None) -> bool:
    return a_from <= (b_to or FAR_FUTURE) and b_from <= (a_to or FAR_FUTURE)


def _jsonable(v: Any) -> Any:
    return json.loads(json.dumps(v, default=str))


def _jdict(v: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = _jsonable(v)
    return out


def _snapshot(row: RuleVersion) -> dict[str, Any]:
    snap: dict[str, Any] = {"ref": f"{row.rule_key}@v{row.version}", "value": row.value,
                            "effective_from": row.effective_from,
                            "effective_to": row.effective_to, "status": row.status,
                            "source_url": row.source_url, "source_ref": row.source_ref}
    if row.firm_id is not None:
        snap.update(firm_id=row.firm_id, engagement_id=row.engagement_id,
                    based_on_id=row.based_on_id)
    return _jdict(snap)


def _audit(s: Session, user: str | None, action: str, entity: str, entity_id: str | None,
           old: dict[str, Any] | None, new: dict[str, Any] | None) -> None:
    s.add(AuditLog(user_id=user, action=action, entity=entity, entity_id=entity_id,
                   old=old, new=new))


def propose(s: Session, *, rule_key: str, value: Any, effective_from: date,
            effective_to: date | None = None, source_url: str | None = None,
            source_ref: str = "", unit: str = "", proposed_by: str | None = None,
            comment: str | None = None, source_doc_hash: str | None = None,
            firm_id: str | None = None, engagement_id: str | None = None,
            based_on_id: str | None = None) -> RuleVersion:
    """A new version in status ``proposed`` (any change needs Tax Partner approval).

    Version numbers are global per rule_key (defaults and every firm), so ``rule_key@vN``
    identifies exactly one row and results never confuse two firms' versions.
    """
    if not KEY_RE.match(rule_key):
        raise RuleError(f"Invalid rule key '{rule_key}'")
    if effective_to is not None and effective_to < effective_from:
        raise RuleError("effective_to is before effective_from")
    if source_url is not None and not source_url.startswith("https://"):
        raise RuleError("source_url must be an https:// URL")
    versions = s.scalars(select(RuleVersion.version).where(RuleVersion.rule_key == rule_key)).all()
    row = RuleVersion(rule_key=rule_key, version=max(versions, default=0) + 1,
                      value=_jsonable(value), effective_from=effective_from,
                      effective_to=effective_to, source_url=source_url,
                      source_doc_hash=source_doc_hash, source_ref=source_ref, unit=unit,
                      domain=domain_of(rule_key), status="proposed", proposed_by=proposed_by,
                      comment=comment, firm_id=firm_id, engagement_id=engagement_id,
                      based_on_id=based_on_id)
    s.add(row)
    s.flush()
    _audit(s, proposed_by, "rule_propose", "rule_version", row.id, None, _snapshot(row))
    s.commit()
    invalidate()
    return row


# D43: inside a firm, tax rules need the firm's Tax Partner; methodology rules its (audit /
# assurance) Partner. Admin manages the firm but never signs off rules.
TAX_DOMAINS = frozenset({"VAT", "INPUT_VAT", "CT", "TRN", "LEGAL_REF"})
FIRM_TAX_APPROVERS = ("TaxPartner",)
FIRM_METHOD_APPROVERS = ("Partner",)
FIRM_PROPOSER_ROLES = ("Partner", "TaxPartner", "Manager")


def firm_approver_roles(rule_key: str) -> tuple[str, ...]:
    return FIRM_TAX_APPROVERS if domain_of(rule_key) in TAX_DOMAINS else FIRM_METHOD_APPROVERS


def check_comment(comment: str | None) -> str:
    text = (comment or "").strip()
    if len(text) < MIN_COMMENT:
        raise RuleError(f"A comment of at least {MIN_COMMENT} characters is mandatory")
    return text


def check_firm_approver(rule_key: str, roles: Iterable[str], comment: str | None) -> str:
    need = firm_approver_roles(rule_key)
    if not set(roles).intersection(need):
        kind = "tax" if need == FIRM_TAX_APPROVERS else "methodology"
        raise RuleError(f"Only the firm's {' or '.join(need)} can approve {kind} rule "
                        f"'{rule_key}' for the firm", 403)
    return check_comment(comment)


def _check_approver(rule_key: str, roles: Iterable[str], comment: str | None) -> str:
    """Approver of a shared default (platform user): same domain split as a firm (D47)."""
    need = firm_approver_roles(rule_key)
    if not set(roles).intersection(need):
        kind = "tax" if need == FIRM_TAX_APPROVERS else "methodology"
        raise RuleError(f"Only a {' or '.join(need)} can approve or reject {kind} rule "
                        f"'{rule_key}' (Admin never approves rules)", 403)
    return check_comment(comment)


@dataclass
class Approval:
    rule: Rule
    closed: list[dict[str, Any]] = field(default_factory=list)
    superseded: list[dict[str, Any]] = field(default_factory=list)
    stale: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return _jdict({"rule": rule_dict(self.rule), "closed": self.closed,
                          "superseded": self.superseded, "stale": self.stale})


DEFAULTS_ARE_SHARED = ("Default rules are shared by every firm; approve one for your firm with "
                       "POST /v1/firm/rules/{rule_key}/approve or propose a firm override with "
                       "POST /v1/firm/rules/{rule_key}/override")


def _row_for(s: Session, version_id: str, firm_id: str | None) -> RuleVersion:
    """The version a caller may act on: a firm user only sees its own firm's rows."""
    row = s.get(RuleVersion, version_id)
    if row is None or (row.firm_id is not None and row.firm_id != firm_id):
        raise RuleError("Rule version not found", 404)  # never reveal another firm's rows
    if row.firm_id is None and firm_id is not None:
        raise RuleError(DEFAULTS_ARE_SHARED, 403)
    return row


def _same_scope(a: RuleVersion, b: RuleVersion) -> bool:
    return a.firm_id == b.firm_id and a.engagement_id == b.engagement_id


def _scope_engagements(s: Session, row: RuleVersion) -> list[str] | None:
    """Engagements whose results a version can affect (None = all: a shared default)."""
    if row.firm_id is None:
        return None
    if row.engagement_id is not None:
        return [row.engagement_id]
    q = select(Engagement.id).join(Client, Client.id == Engagement.client_id) \
        .where(Client.firm_id == row.firm_id)
    return list(s.scalars(q).all())


def approve(s: Session, version_id: str, *, user_id: str, roles: Iterable[str],
            comment: str | None, firm_id: str | None = None) -> Approval:
    """Approve a version. ``firm_id`` is the acting user's firm (None = platform user)."""
    row = _row_for(s, version_id, firm_id)
    text = (check_firm_approver(row.rule_key, roles, comment) if row.firm_id is not None
            else _check_approver(row.rule_key, roles, comment))
    if row.status not in OPEN_STATUSES:
        raise RuleError(f"{row.rule_key}@v{row.version} is {row.status}; only proposed or "
                        "pending_verification versions can be approved", 409)
    every = s.scalars(select(RuleVersion).where(RuleVersion.rule_key == row.rule_key,
                                                RuleVersion.id != row.id)).all()
    others = [o for o in every if _same_scope(o, row)]
    new_from, new_to = row.effective_from, row.effective_to
    to_close: list[RuleVersion] = []
    for o in others:
        if o.status != "approved" or not _overlaps(o.effective_from, o.effective_to,
                                                   new_from, new_to):
            continue
        # The only allowed overlap: an earlier version still open past new_from, closed at
        # new_from - 1 (and not extending beyond a bounded new version).
        if o.effective_from < new_from and (new_to is None or (o.effective_to is not None
                                                                and o.effective_to <= new_to)):
            to_close.append(o)
            continue
        raise RuleError(f"{row.rule_key}@v{row.version} ({new_from} to {new_to or 'open'}) "
                        f"overlaps approved {o.rule_key}@v{o.version} ({o.effective_from} to "
                        f"{o.effective_to or 'open'})", 409)
    out_closed: list[dict[str, Any]] = []
    out_superseded: list[dict[str, Any]] = []
    lost: list[tuple[str, date, date | None]] = []  # (ref, from, to) that lost coverage
    for o in [*to_close, *[x for x in others if x.status == "pending_verification"
                           and _overlaps(x.effective_from, x.effective_to, new_from, new_to)]]:
        old = _snapshot(o)
        ref = f"{o.rule_key}@v{o.version}"
        lo = max(o.effective_from, new_from)
        hi = min(o.effective_to or FAR_FUTURE, new_to or FAR_FUTURE)
        if o.effective_from < new_from and (new_to is None or (o.effective_to is not None
                                                                and o.effective_to <= new_to)):
            o.effective_to = new_from - timedelta(days=1)
            out_closed.append({"ref": ref, "effective_to": o.effective_to})
        else:
            o.status = "superseded"
            out_superseded.append({"ref": ref})
        lost.append((ref, lo, None if hi == FAR_FUTURE else hi))
        _audit(s, user_id, "rule_close", "rule_version", o.id, old, _snapshot(o))
    if row.firm_id is not None:  # the override hides lower layers for its firm / engagement
        for o in every:
            lower = o.firm_id is None or (row.engagement_id is not None
                                          and o.firm_id == row.firm_id
                                          and o.engagement_id is None)
            if lower and o.status in RESOLVABLE and _overlaps(o.effective_from, o.effective_to,
                                                               new_from, new_to):
                lo = max(o.effective_from, new_from)
                hi = min(o.effective_to or FAR_FUTURE, new_to or FAR_FUTURE)
                lost.append((f"{o.rule_key}@v{o.version}", lo, None if hi == FAR_FUTURE else hi))
    old_row = _snapshot(row)
    row.status = "approved"
    row.approved_by = user_id
    row.approved_at = datetime.now(UTC)
    row.comment = text
    s.flush()
    _audit(s, user_id, "rule_approve", "rule_version", row.id, old_row, _snapshot(row))
    stale = mark_stale(s, lost, user_id=user_id, reason=f"superseded by "
                       f"{row.rule_key}@v{row.version}",
                       engagement_ids=_scope_engagements(s, row)) if lost else []
    s.commit()
    invalidate()
    return Approval(rule=_from_row(row), closed=out_closed, superseded=out_superseded,
                    stale=stale)


def reject(s: Session, version_id: str, *, user_id: str, roles: Iterable[str],
           comment: str | None, firm_id: str | None = None) -> RuleVersion:
    row = _row_for(s, version_id, firm_id)
    text = (check_firm_approver(row.rule_key, roles, comment) if row.firm_id is not None
            else _check_approver(row.rule_key, roles, comment))
    if row.status != "proposed":
        raise RuleError(f"{row.rule_key}@v{row.version} is {row.status}; only proposed "
                        "versions can be rejected", 409)
    old = _snapshot(row)
    row.status, row.comment = "rejected", text
    s.flush()
    _audit(s, user_id, "rule_reject", "rule_version", row.id, old, _snapshot(row))
    s.commit()
    invalidate()
    return row


# --------------------------------------------------------------------------- STALE marking
def refs_in(obj: Any) -> set[str]:
    """Every ``rule_key@vN`` referenced in a result (``ref`` values and ref-shaped keys)."""
    out: set[str] = set()

    def walk(o: Any) -> None:
        if isinstance(o, Mapping):
            for k, v in o.items():
                if isinstance(k, str) and REF_RE.match(k):
                    out.add(k)
                if k == "ref" and isinstance(v, str) and REF_RE.match(v):
                    out.add(v)
                walk(v)
        elif isinstance(o, list | tuple):
            for v in o:
                walk(v)

    walk(obj)
    return out


def result_period(ds: Dataset | None, eng: Engagement | None) -> tuple[date, date] | None:
    prof = (ds.profile or {}) if ds is not None else {}
    lo, hi = _d(prof.get("min_posting_date")), _d(prof.get("max_posting_date"))
    if lo and hi:
        return lo, hi
    if eng is not None and eng.fye is not None:
        fye = eng.fye
        try:
            start = fye.replace(year=fye.year - 1) + timedelta(days=1)
        except ValueError:  # 29 Feb
            start = fye.replace(year=fye.year - 1, day=28) + timedelta(days=1)
        return start, fye
    return None


def _results(s: Session, engagement_ids: Collection[str] | None = None
             ) -> Iterator[tuple[str, Any]]:
    for model, kind in ((Sample, "sample"), (JeRun, "je_run"), (InputVatRun, "input_vat_run")):
        q = select(model).where(model.status != "STALE")
        if engagement_ids is not None:
            q = q.where(model.engagement_id.in_(list(engagement_ids)))
        for r in s.scalars(q).all():
            yield kind, r


def mark_stale(s: Session, lost: Sequence[tuple[str, date, date | None]], *,
               user_id: str | None, reason: str,
               engagement_ids: Collection[str] | None = None) -> list[dict[str, Any]]:
    """Mark STALE every current result that used a ref for a period that lost coverage.

    ``engagement_ids`` limits the search (a firm / engagement override only affects its own
    firm's or engagement's results, D42); None = every result (a shared default changed).
    """
    out: list[dict[str, Any]] = []
    if engagement_ids is not None and not engagement_ids:
        return out
    for kind, r in _results(s, engagement_ids):
        used = refs_in({"u": r.rule_versions_used, "r": getattr(r, "result", None)})
        hits = [(ref, lo, hi) for ref, lo, hi in lost if ref in used]
        if not hits:
            continue
        period = result_period(s.get(Dataset, r.dataset_id), s.get(Engagement, r.engagement_id))
        refs = sorted({ref for ref, lo, hi in hits
                       if period is None or _overlaps(period[0], period[1], lo, hi)})
        if not refs:
            continue
        r.status = "STALE"
        item = {"kind": kind, "id": r.id, "engagement_id": r.engagement_id, "refs": refs}
        out.append(item)
        _audit(s, user_id, "stale", kind, r.id, {"status": "current"},
               {"status": "STALE", "refs": refs, "reason": reason})
    return out


# --------------------------------------------------------------------------- views
def rule_dict(r: Rule) -> dict[str, Any]:
    d: dict[str, Any] = {"id": r.id, "ref": r.ref, "rule_key": r.rule_key,
                         "version": r.version, "domain": r.domain, "value": r.value,
                         "unit": r.unit, "effective_from": r.effective_from,
                         "effective_to": r.effective_to, "status": r.status,
                         "source_ref": r.source_ref, "source_url": r.source_url}
    if r.firm_id is not None or r.firm_approved:
        d.update(layer=r.layer, firm_id=r.firm_id, engagement_id=r.engagement_id,
                 firm_approved=r.firm_approved)
    return _jdict(d)


def list_versions(s: Session, *, rule_key: str | None = None, domain: str | None = None,
                  status: str | None = None, firm_id: str | None = None) -> list[dict[str, Any]]:
    """Shared defaults, plus ``firm_id``'s own overrides - never another firm's rows."""
    q = select(RuleVersion).where(RuleVersion.firm_id.is_(None) if firm_id is None
                                  else (RuleVersion.firm_id.is_(None)
                                        | (RuleVersion.firm_id == firm_id)))
    if rule_key:
        q = q.where(RuleVersion.rule_key == rule_key)
    if domain:
        q = q.where(RuleVersion.domain == domain.upper())
    if status:
        q = q.where(RuleVersion.status == status)
    rows = s.scalars(q.order_by(RuleVersion.rule_key, RuleVersion.version)).all()
    return [rule_dict(_from_row(r)) for r in rows]
