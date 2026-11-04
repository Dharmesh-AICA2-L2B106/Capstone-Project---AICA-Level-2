"""Input-VAT recovery checks: FTA Decisions 13 and 17 of 2026 (SPEC 3.8, prompt 3.12).

Deterministic Decimal checks. No AI is used. Every date, period and threshold comes from
``input_vat.*`` rules valid on the deduction date. The checks support testing: whether a
condition is met stays an auditor or tax judgement.

Checks (D40):

* ``unverified_supplier``: a deduction on or after the effective date where the supplier is
  not in the register, has no verification date, was verified after the deduction, or was
  verified more than ``revalidate_months`` before it.
* ``spend_threshold``: the supplier's rolling 12-month gross purchases exceed
  ``spend_threshold`` and it has no bank evidence. One exception per supplier, on the line
  where the total first crosses the threshold.
* ``risk_indicator_unexplained``: the register shows risk indicators but no explanation.
* ``employee_expense``: lines in accounts mapped to a Decision 17 category, listed for
  condition testing.
* ``staff_cost_unmapped``: an account that looks like staff cost but is not mapped.

``effective_date_override`` is TEST-ONLY (D4). It moves the effective date, and each rule is
looked up on the deduction date shifted by the same number of days, so the test data from 2025
uses the same rule versions as live data from 2026.
"""

from __future__ import annotations

import csv
import io
import re
from collections import defaultdict, deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from app.services import jobs
from app.services.sampling import jsonable, money
from app.services.vat import _Rules, round2
from app.version import ENGINE_NAME, ENGINE_VERSION

IMPLEMENTED_BY_PROMPT = "3.12"

ZERO = Decimal(0)
ROLLING_MONTHS = 12  # "rolling 12-month spend" (SPEC 3.8); the period itself is not a rule
K_EFF = "input_vat.verification.effective_date"
K_THRESHOLD = "input_vat.verification.spend_threshold"
K_MONTHS = "input_vat.verification.revalidate_months"
K_BELOW = "input_vat.verification.exception_below"
K_CATS = "input_vat.employee_expense.categories"
CHECKS = ("unverified_supplier", "spend_threshold", "risk_indicator_unexplained",
          "employee_expense", "staff_cost_unmapped")
COLUMNS = ("row_no", "line_id", "voucher_no", "entry_date", "posting_date", "account_code",
           "account_name", "debit", "party_id", "party_name", "vat_amount", "vat_code",
           "expense_category")
STAFF_RE = re.compile(r"\b(staff|employee|employees|salar(y|ies)|wages?)\b", re.I)
MAX_REGISTER_ROWS = 20_000


class InputVatError(ValueError):
    def __init__(self, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# --------------------------------------------------------------------------- inputs
@dataclass(frozen=True)
class Supplier:
    supplier_id: str
    supplier_name: str | None = None
    trn: str | None = None
    verified_on: date | None = None
    evidence_ref: str | None = None
    risk_indicators: tuple[str, ...] = ()
    explanation: str | None = None
    bank_evidence_ref: str | None = None


_ALIASES = {
    "supplier_id": ("supplier_id", "party_id", "supplier_code", "vendor_id"),
    "supplier_name": ("supplier_name", "party_name", "name", "vendor_name"),
    "trn": ("trn",),
    "verified_on": ("verified_on", "verification_date"),
    "evidence_ref": ("evidence_ref", "verification_ref"),
    "risk_indicators": ("risk_indicators", "risk_indicator"),
    "explanation": ("explanation", "risk_explanation"),
    "bank_evidence_ref": ("bank_evidence_ref", "bank_evidence"),
}


def _txt(v: Any) -> str | None:
    s = str(v).strip() if v is not None else ""
    return s or None


def parse_register_csv(data: bytes) -> tuple[list[Supplier], list[dict[str, Any]]]:
    """Parse a supplier verification register CSV. Returns (suppliers, errors)."""
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise InputVatError("The register must be a UTF-8 CSV file.") from None
    reader = csv.DictReader(io.StringIO(text))
    heads = {h.strip().lower(): h for h in (reader.fieldnames or [])}
    col = {k: next((heads[a] for a in al if a in heads), None) for k, al in _ALIASES.items()}
    if col["supplier_id"] is None:
        raise InputVatError("The register needs a supplier_id (or party_id) column.")
    out: list[Supplier] = []
    errors: list[dict[str, Any]] = []
    seen: set[str] = set()
    for i, row in enumerate(reader, start=2):
        if i - 1 > MAX_REGISTER_ROWS:
            raise InputVatError(f"The register has more than {MAX_REGISTER_ROWS:,} rows.")

        def get(k: str, row: Mapping[str, Any] = row) -> str | None:
            c = col[k]
            return _txt(row.get(c)) if c else None

        sid = get("supplier_id")
        if not sid:
            errors.append({"row": i, "column": col["supplier_id"],
                           "message": "Supplier ID is blank - fill it in or delete the row."})
            continue
        if sid in seen:
            errors.append({"row": i, "column": col["supplier_id"],
                           "message": f"Supplier {sid} appears twice - keep one row."})
            continue
        vo = get("verified_on")
        try:
            vdate = date.fromisoformat(vo) if vo else None
        except ValueError:
            errors.append({"row": i, "column": col["verified_on"],
                           "message": f"Verified-on date '{vo}' is not YYYY-MM-DD."})
            continue
        seen.add(sid)
        risks = tuple(x.strip() for x in re.split(r"[;|]", get("risk_indicators") or "")
                      if x.strip())
        out.append(Supplier(sid, get("supplier_name"), get("trn"), vdate, get("evidence_ref"),
                            risks, get("explanation"), get("bank_evidence_ref")))
    return out, errors


@dataclass(frozen=True)
class Params:
    effective_date_override: date | None = None

    @classmethod
    def build(cls, overrides: Mapping[str, Any] | None) -> Params:
        o = dict(overrides or {})
        unknown = set(o) - {"effective_date_override"}
        if unknown:
            raise InputVatError(f"Unknown parameter(s): {', '.join(sorted(unknown))}.")
        v = o.get("effective_date_override")
        try:
            d = v if isinstance(v, date) or v is None else date.fromisoformat(str(v))
        except ValueError:
            raise InputVatError("effective_date_override must be YYYY-MM-DD.") from None
        return cls(d)


# --------------------------------------------------------------------------- engine
def add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    y, m = d.year + y, m + 1
    for day in (d.day, 30, 29, 28):
        try:
            return date(y, m, day)
        except ValueError:
            continue
    raise AssertionError("unreachable")  # pragma: no cover


def _dec(v: Any) -> Decimal:
    if v is None or v == "":
        return ZERO
    try:
        return Decimal(str(v))
    except InvalidOperation:
        return ZERO


def _date(v: Any) -> date | None:
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


@dataclass
class _Ctx:
    rules: _Rules = field(default_factory=_Rules)
    shift: timedelta = timedelta(0)
    effective: date | None = None
    warnings: list[str] = field(default_factory=list)

    def value(self, key: str, d: date) -> Any:
        r = self.rules.get(key, d + self.shift)
        return None if r is None else r.value

    def ref(self, key: str, d: date) -> str | None:
        r = self.rules.get(key, d + self.shift)
        return None if r is None else r.ref


def _effective(rules: _Rules, override: date | None, today: date) -> tuple[date | None,
                                                                        timedelta]:
    r = rules.get(K_EFF, today)
    if r is None:
        return override, timedelta(0)
    eff = _date(r.value) or r.effective_from
    if override is None:
        return eff, timedelta(0)
    return override, eff - override


def run_input_vat(rows: Iterable[Mapping[str, Any]], register: Sequence[Supplier],
                  mapping: Mapping[str, str], params: Params, *,
                  today: date | None = None) -> dict[str, Any]:
    """Run every check over the purchase lines. Pure function (no database)."""
    ctx = _Ctx()
    eff, ctx.shift = _effective(ctx.rules, params.effective_date_override,
                                today or date.today())
    ctx.effective = eff
    if params.effective_date_override is not None:
        ctx.warnings.append(
            f"TEST-ONLY effective date {eff} used (rule effective date shifted by "
            f"{ctx.shift.days} days). Do not use for a live engagement.")
    if eff is None:
        raise InputVatError(f"Rule '{K_EFF}' is not in the Rules Library.")
    reg = {s.supplier_id: s for s in register}
    lines: list[dict[str, Any]] = []
    accounts: dict[str, dict[str, Any]] = {}
    for i, r in enumerate(rows):
        code = str(r.get("account_code") or "").strip()
        vat = _dec(r.get("vat_amount"))
        cat = _txt(r.get("expense_category"))
        acc = accounts.setdefault(code, {"account_code": code,
                                         "account_name": _txt(r.get("account_name")),
                                         "vat_lines": 0, "categorised_lines": 0})
        if cat:
            acc["categorised_lines"] += 1
        debit = _dec(r.get("debit"))
        if vat <= 0 or debit <= 0:
            continue
        acc["vat_lines"] += 1
        d = _date(r.get("posting_date")) or _date(r.get("entry_date"))
        lines.append({
            "line_ref": str(r.get("line_id") or r.get("row_no") or i + 1),
            "voucher_no": _txt(r.get("voucher_no")), "date": d, "account_code": code,
            "party_id": _txt(r.get("party_id")), "party_name": _txt(r.get("party_name")),
            "net": debit, "vat_amount": vat, "gross": debit + vat, "category": cat,
        })
    lines.sort(key=lambda x: (x["date"] or date.min, x["line_ref"]))
    exc: list[dict[str, Any]] = []
    undated = sum(1 for ln in lines if ln["date"] is None)
    if undated:
        ctx.warnings.append(f"{undated} input-VAT line(s) have no date and were not tested "
                            "for supplier verification.")
    _supplier_checks(lines, reg, ctx, eff, exc)
    ee, by_cat = _employee_checks(lines, accounts, mapping, ctx, eff, exc)
    in_scope = [ln for ln in lines if ln["date"] and ln["date"] >= eff]
    summary = []
    for c in CHECKS:
        items = [e for e in exc if e["check"] == c]
        summary.append({"check": c, "lines": len(items),
                        "value": money(sum((e["amount"] or ZERO for e in items), ZERO))})
    n_ex = sum(1 for e in exc if e["check"] != "employee_expense")
    conclusion = (f"{n_ex} supplier/mapping exception(s) and {len(ee)} employee-expense line(s) "
                  f"listed for testing; whether the conditions are met is an auditor / tax "
                  f"judgement.")
    rules_used = dict(ctx.rules.used)
    return {
        "engine_version": f"{ENGINE_NAME} {ENGINE_VERSION}",
        "effective_date": eff,
        "effective_date_override": params.effective_date_override,
        "parameters": {"effective_date_override": params.effective_date_override,
                       "rolling_months": ROLLING_MONTHS},
        "population": {"input_vat_lines": len(lines), "in_scope_lines": len(in_scope),
                       "in_scope_vat": money(sum((x["vat_amount"] for x in in_scope), ZERO)),
                       "suppliers": len({x["party_id"] for x in lines if x["party_id"]}),
                       "register_suppliers": len(reg), "mapped_accounts": len(mapping)},
        "summary": summary,
        "exceptions": exc,
        "employee_expense_by_category": by_cat,
        "conclusion": conclusion,
        "basis": ("FTA Decision No. 13 of 2026 (supplier verification) and No. 17 of 2026 "
                  "(employee expenses) - values from the Rules Library; checks support testing "
                  "only."),
        "warnings": ctx.warnings,
        "rule_versions_used": rules_used,
        "rules_pending_verification": ctx.rules.pending,
    }


def _supplier_checks(lines: list[dict[str, Any]], reg: Mapping[str, Supplier], ctx: _Ctx,
                     eff: date, exc: list[dict[str, Any]]) -> None:
    by_sup: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ln in lines:
        if ln["party_id"] and ln["date"]:
            by_sup[ln["party_id"]].append(ln)
    no_party = [ln for ln in lines if not ln["party_id"] and ln["date"] and ln["date"] >= eff]
    if no_party:
        ctx.warnings.append(f"{len(no_party)} input-VAT line(s) on or after {eff} have no "
                            "supplier ID; add the supplier to test verification.")
    for sid in sorted(by_sup):
        sup = reg.get(sid)
        window: deque[dict[str, Any]] = deque()
        total = ZERO
        crossed = False
        risk_done = False
        for ln in by_sup[sid]:
            d = ln["date"]
            window.append(ln)
            total += ln["gross"]
            start = add_months(d, -ROLLING_MONTHS)
            while window and window[0]["date"] <= start:
                total -= window.popleft()["gross"]
            if d < eff:
                continue
            below = ctx.value(K_BELOW, d)
            base = {"line_ref": ln["line_ref"], "voucher_no": ln["voucher_no"],
                    "date": d, "party_id": sid, "party_name": ln["party_name"],
                    "amount": ln["gross"], "vat_amount": ln["vat_amount"]}
            reason = _verification_gap(sup, d, ctx)
            if reason:
                exc.append({**base, "check": "unverified_supplier", "reason": reason,
                            "below_exception_threshold": (below is not None
                                                          and ln["gross"] < _dec(below)),
                            "rule_refs": [x for x in (ctx.ref(K_EFF, d), ctx.ref(K_MONTHS, d))
                                          if x]})
            thr = ctx.value(K_THRESHOLD, d)
            if (not crossed and thr is not None and total > _dec(thr)
                    and not (sup and sup.bank_evidence_ref)):
                crossed = True
                exc.append({**base, "check": "spend_threshold", "rolling_total": money(total),
                            "reason": (f"Rolling {ROLLING_MONTHS}-month gross purchases reach "
                                       f"AED {round2(total):,} (> {round2(_dec(thr)):,}) on {d}; "
                                       "no bank-account evidence in the supplier register."),
                            "rule_refs": [x for x in (ctx.ref(K_THRESHOLD, d),) if x]})
            if sup and sup.risk_indicators and not sup.explanation and not risk_done:
                risk_done = True
                exc.append({**base, "check": "risk_indicator_unexplained",
                            "reason": (f"Risk indicator(s) {', '.join(sup.risk_indicators)} "
                                       "recorded without a written explanation."),
                            "rule_refs": [x for x in (ctx.ref(K_EFF, d),) if x]})


def _verification_gap(sup: Supplier | None, d: date, ctx: _Ctx) -> str | None:
    if sup is None:
        return (f"Input VAT deducted on {d}; supplier is not in the verification register "
                "(first-time supplier?).")
    if sup.verified_on is None:
        return f"Input VAT deducted on {d}; supplier has no verification date in the register."
    if sup.verified_on > d:
        return (f"Input VAT deducted on {d}; supplier was verified later, on "
                f"{sup.verified_on}.")
    months = ctx.value(K_MONTHS, d)
    if months is not None and sup.verified_on <= add_months(d, -int(months)):
        return (f"Input VAT deducted on {d}; last verification {sup.verified_on} is older than "
                f"{int(months)} months.")
    return None


def _employee_checks(lines: list[dict[str, Any]], accounts: Mapping[str, dict[str, Any]],
                     mapping: Mapping[str, str], ctx: _Ctx, eff: date,
                     exc: list[dict[str, Any]]) -> tuple[list[dict[str, Any]],
                                                         list[dict[str, Any]]]:
    cats = ctx.value(K_CATS, eff) or []
    ref = ctx.ref(K_CATS, eff)
    bad = sorted({c for c in mapping.values() if c not in cats})
    if bad:
        ctx.warnings.append(f"Mapped categories not in rule {ref or K_CATS}: {', '.join(bad)}.")
    ee: list[dict[str, Any]] = []
    for ln in lines:
        cat = mapping.get(ln["account_code"])
        if cat is None:
            continue
        item = {"line_ref": ln["line_ref"], "voucher_no": ln["voucher_no"], "date": ln["date"],
                "party_id": ln["party_id"], "party_name": ln["party_name"],
                "amount": ln["gross"], "vat_amount": ln["vat_amount"],
                "check": "employee_expense", "category": cat,
                "account_code": ln["account_code"],
                "before_effective_date": bool(ln["date"] and ln["date"] < eff),
                "reason": (f"Employee expense ({cat}) with input VAT recovered - test the "
                           "Decision 17/2026 conditions for this category."),
                "rule_refs": [x for x in (ref,) if x]}
        ee.append(item)
        exc.append(item)
    by_cat = []
    for c in [*cats, *bad]:
        items = [e for e in ee if e["category"] == c]
        by_cat.append({"category": c, "lines": len(items),
                       "vat_amount": money(sum((e["vat_amount"] for e in items), ZERO)),
                       "in_rule": c in cats})
    for code in sorted(accounts):
        a = accounts[code]
        if code in mapping or not code:
            continue
        staffish = bool(a["account_name"] and STAFF_RE.search(a["account_name"]))
        if a["categorised_lines"] or (staffish and a["vat_lines"]):
            exc.append({"line_ref": None, "check": "staff_cost_unmapped", "account_code": code,
                        "party_id": None, "amount": None,
                        "reason": (f"Account {code} {a['account_name'] or ''} looks like staff "
                                   "cost but is not mapped to a Decision 17 category - map it "
                                   "or record why it is out of scope.").replace("  ", " "),
                        "rule_refs": [x for x in (ref,) if x]})
    return ee, by_cat


# --------------------------------------------------------------------------- storage
def _supplier_dict(s: Supplier) -> dict[str, Any]:
    return {"supplier_id": s.supplier_id, "supplier_name": s.supplier_name, "trn": s.trn,
            "verified_on": s.verified_on, "evidence_ref": s.evidence_ref,
            "risk_indicators": list(s.risk_indicators), "explanation": s.explanation,
            "bank_evidence_ref": s.bank_evidence_ref}


def replace_register(engagement_id: str, suppliers: Sequence[Supplier], *,
                     user_id: str | None) -> int:
    """Replace the engagement's supplier register (audit-logged). Returns the row count."""
    from sqlalchemy import delete

    from app.core.db import session_factory
    from app.models import AuditLog, SupplierRegister

    with session_factory()() as s:
        old = s.query(SupplierRegister).filter_by(engagement_id=engagement_id).count()
        s.execute(delete(SupplierRegister).where(SupplierRegister.engagement_id == engagement_id))
        for x in suppliers:
            s.add(SupplierRegister(engagement_id=engagement_id, supplier_id=x.supplier_id,
                                   supplier_name=x.supplier_name, trn=x.trn,
                                   verified_on=x.verified_on, evidence_ref=x.evidence_ref,
                                   risk_indicators=list(x.risk_indicators) or None,
                                   explanation=x.explanation,
                                   bank_evidence_ref=x.bank_evidence_ref))
        s.add(AuditLog(user_id=user_id, action="supplier_register_replace",
                       entity="engagement", entity_id=engagement_id,
                       old={"rows": old}, new={"rows": len(suppliers)}))
        s.commit()
    return len(suppliers)


def load_register(engagement_id: str) -> list[Supplier]:
    from app.core.db import session_factory
    from app.models import SupplierRegister

    with session_factory()() as s:
        rows = (s.query(SupplierRegister).filter_by(engagement_id=engagement_id)
                .order_by(SupplierRegister.supplier_id).all())
        return [Supplier(r.supplier_id, r.supplier_name, r.trn, r.verified_on, r.evidence_ref,
                         tuple(r.risk_indicators or ()), r.explanation, r.bank_evidence_ref)
                for r in rows]


def register_view(engagement_id: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = jsonable([_supplier_dict(x) for x in load_register(engagement_id)])
    return out


def categories(on: date | None = None) -> list[str]:
    """Decision 17 categories valid on ``on`` (default: the rule effective date)."""
    rules = _Rules()
    eff_rule = rules.get(K_EFF, date.today())
    when = on or (_date(eff_rule.value) if eff_rule else None) or date.today()
    r = rules.get(K_CATS, when)
    if r is None:
        raise InputVatError(f"Rule '{K_CATS}' has no version effective on {when}.")
    return [str(c) for c in r.value]


def replace_mapping(engagement_id: str, items: Sequence[Mapping[str, str]], *,
                    user_id: str | None) -> dict[str, str]:
    """Replace the account -> Decision 17 category mapping (categories checked)."""
    from sqlalchemy import delete

    from app.core.db import session_factory
    from app.models import AuditLog, ExpenseMapping

    allowed = categories()
    mapping: dict[str, str] = {}
    for i, it in enumerate(items):
        code, cat = str(it["account_code"]).strip(), str(it["category"]).strip()
        if not code:
            raise InputVatError(f"Item {i + 1}: account_code is blank.")
        if cat not in allowed:
            raise InputVatError(f"Item {i + 1}: category '{cat}' is not one of "
                                f"{', '.join(allowed)} (rule {K_CATS}).")
        if code in mapping:
            raise InputVatError(f"Item {i + 1}: account {code} is mapped twice.")
        mapping[code] = cat
    with session_factory()() as s:
        before = {m.account_code: m.category
                  for m in s.query(ExpenseMapping).filter_by(engagement_id=engagement_id)}
        s.execute(delete(ExpenseMapping).where(ExpenseMapping.engagement_id == engagement_id))
        for code, cat in mapping.items():
            s.add(ExpenseMapping(engagement_id=engagement_id, account_code=code, category=cat))
        s.add(AuditLog(user_id=user_id, action="expense_mapping_replace", entity="engagement",
                       entity_id=engagement_id, old=before, new=mapping))
        s.commit()
    return mapping


def load_mapping(engagement_id: str) -> dict[str, str]:
    from app.core.db import session_factory
    from app.models import ExpenseMapping

    with session_factory()() as s:
        return {m.account_code: m.category
                for m in s.query(ExpenseMapping).filter_by(engagement_id=engagement_id)}


# --------------------------------------------------------------------------- runs (job)
def start_run(dataset_id: str, overrides: Mapping[str, Any] | None, *,
              user_id: str | None) -> tuple[str, str]:
    """Create an InputVatRun and queue the ``input_vat_check`` job; (run_id, job_id)."""
    from app.core.db import session_factory
    from app.models import InputVatRun
    from app.services.datasets import assert_usable

    ds = assert_usable(dataset_id)
    params = Params.build(overrides)
    with session_factory()() as s:
        run = InputVatRun(engagement_id=ds.engagement_id, dataset_id=ds.id,
                          parameters=jsonable({"effective_date_override":
                                               params.effective_date_override}),
                          engine_version=ENGINE_VERSION, status="queued", created_by=user_id)
        s.add(run)
        s.commit()
        run_id = run.id
    job_id = jobs.enqueue("input_vat_check", {"run_id": run_id},
                          job_type="input_vat_check", engagement_id=ds.engagement_id,
                          created_by=user_id)
    with session_factory()() as s:
        r = s.get(InputVatRun, run_id)
        if r is not None and r.job_id is None:
            r.job_id = job_id
            s.commit()
    return run_id, job_id


@jobs.task("input_vat_check")
def input_vat_task(job_id: str, *, run_id: str) -> str:
    from app.core.db import session_factory
    from app.models import InputVatRun

    try:
        _execute(run_id, job_id)
    except Exception as exc:
        with session_factory()() as s:
            r = s.get(InputVatRun, run_id)
            if r is not None:
                r.status = "cancelled" if isinstance(exc, jobs.JobCancelled) else "failed"
                s.commit()
        raise
    return f"input_vat_run:{run_id}"


def _execute(run_id: str, job_id: str) -> None:
    from pathlib import Path

    from sqlalchemy import update

    from app.core.db import session_factory
    from app.models import Dataset, InputVatRun
    from app.services.importer import read_parquet_rows

    with session_factory()() as s:
        run = s.get(InputVatRun, run_id)
        assert run is not None
        ds = s.get(Dataset, run.dataset_id)
        assert ds is not None
        path, eng_id, ds_id = Path(ds.parquet_ref or ""), run.engagement_id, run.dataset_id
        params = Params.build(run.parameters)
    jobs.set_progress(job_id, 10)
    register, mapping = load_register(eng_id), load_mapping(eng_id)
    jobs.set_progress(job_id, 30)
    try:
        res = run_input_vat(read_parquet_rows(path, columns=COLUMNS), register, mapping, params)
    except InputVatError as exc:
        raise jobs.JobError(exc.message, exc.status_code) from None
    jobs.set_progress(job_id, 80)
    res.update({"input_vat_run_id": run_id, "dataset_id": ds_id, "engagement_id": eng_id,
                "job_id": job_id})
    out = jsonable(res)
    with session_factory()() as s:
        s.execute(update(InputVatRun)
                  .where(InputVatRun.engagement_id == eng_id, InputVatRun.dataset_id == ds_id,
                         InputVatRun.id != run_id, InputVatRun.status == "current")
                  .values(status="superseded"))
        r = s.get(InputVatRun, run_id)
        assert r is not None
        r.rule_versions_used = out["rule_versions_used"]
        r.result = out
        r.status = "current"
        s.commit()


def get_run(run_id: str) -> tuple[str, dict[str, Any]]:
    from app.core.db import session_factory
    from app.models import InputVatRun

    with session_factory()() as s:
        run = s.get(InputVatRun, run_id)
        if run is None:
            raise InputVatError("Input VAT run not found.", 404)
        base = {"input_vat_run_id": run.id, "status": run.status, "job_id": run.job_id,
                "dataset_id": run.dataset_id, "engagement_id": run.engagement_id}
        return run.engagement_id, {**(run.result or {}), **base}


def list_exceptions(run_id: str, *, check: str | None = None, offset: int = 0,
                    limit: int = 100) -> tuple[str, int, list[dict[str, Any]]]:
    eng, res = get_run(run_id)
    items = [e for e in res.get("exceptions") or [] if check is None or e["check"] == check]
    return eng, len(items), items[offset:offset + limit]
