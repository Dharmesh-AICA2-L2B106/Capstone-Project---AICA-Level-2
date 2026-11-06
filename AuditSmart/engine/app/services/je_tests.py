"""Journal-entry testing, ISA 240 (SPEC 3.2, prompt 3.4).

Each GL line is checked against the firm methodology v0.2 §5 criteria. The thresholds come
from the Rules Library (``je.*``) and can be overridden per run. Each line's risk score is
the number of criteria it meets. Lines scoring >= ``je.score.test`` (3) are selected for
testing and score-2 lines are left to judgement; when fewer than ``je.judgement.min_items``
(10) lines are selected, the largest score-2 lines top the selection up. Selection is
never random.

Calendar-based tests use ``calendar.resolve`` for the engagement's client: weekends,
holidays and half-day cut-offs are never hard-coded. No AI is involved in any step.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, time, timedelta
from decimal import Decimal
from typing import Any

from app.services import jobs
from app.services.calendar import CalendarError, CalendarProfile, ResolvedCalendar
from app.services.rules import RuleNotFound, get_rule
from app.services.sampling import jsonable, money
from app.version import ENGINE_NAME, ENGINE_VERSION

IMPLEMENTED_BY_PROMPT = "3.4"

TESTS: dict[str, str] = {
    "non_working_day": "Posted on a non-working day (weekend, holiday or company closure)",
    "after_half_day_cutoff": "Posted after the half-day cut-off",
    "round_sum": "Round-sum amount",
    "period_end": "Posted near the period end",
    "rare_user": "Posted by a user with few entries",
    "senior_user": "Posted by a senior-management or IT user",
    "large_amount": "Amount at or above performance materiality",
    "vague_narration": "Blank or vague narration",
    "manual_sensitive": "Manual entry to revenue or cash",
    "duplicate_invoice": "Same party and invoice number already posted",
    "duplicate_party_amount_date": "Same party, amount and date already posted",
    "unusual_account_pair": "Rarely used account combination",
    "unbalanced_voucher": "Voucher does not balance",
}


class JeTestError(ValueError):
    pass


@dataclass
class _Rules:
    on_date: date | None
    used: dict[str, dict[str, Any]] = field(default_factory=dict)

    def value(self, key: str) -> Any:
        try:
            r = get_rule(key, self.on_date)
        except RuleNotFound:
            raise JeTestError(
                f"The Rules Library has no value for '{key}'. Ask the "
                "methodology owner to add it before running JE tests."
            ) from None
        self.used[key] = {"version": r.version, "value": r.value, "status": r.status, "ref": r.ref}
        return r.value


# parameter name -> rule key (None = request-only parameter)
PARAM_RULES: dict[str, str | None] = {
    "round_multiple": "je.round_sum.multiple",
    "round_min": "je.round_sum.min",
    "period_end_days": "je.period_end.days",
    "rare_user_max_pct": "je.rare_user.max_pct",
    "vague_keywords": "je.vague_narration.keywords",
    "account_pair_min_count": "je.account_pair.min_count",
    "score_test": "je.score.test",
    "score_judgement": "je.score.judgement",
    "judgement_min_items": "je.judgement.min_items",
    "manual_voucher_prefixes": "je.manual_voucher_prefixes",
    "sensitive_account_types": "je.sensitive_account_types",
    "sensitive_account_codes": "je.sensitive_account_codes",
    "senior_users": None,
    "large_amount": None,
    "tests": None,
}


@dataclass
class JeParams:
    period_end: date | None
    round_multiple: Decimal
    round_min: Decimal
    period_end_days: int
    rare_user_max_pct: Decimal
    vague_keywords: tuple[str, ...]
    account_pair_min_count: int
    score_test: int
    score_judgement: int
    judgement_min_items: int
    manual_voucher_prefixes: tuple[str, ...]
    sensitive_account_types: tuple[str, ...]
    sensitive_account_codes: tuple[str, ...]
    senior_users: tuple[str, ...] = ()
    large_amount: Decimal | None = None
    tests: tuple[str, ...] = tuple(TESTS)
    sources: dict[str, str] = field(default_factory=dict)
    rules_used: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def build(
        cls,
        period_end: date | None,
        overrides: Mapping[str, Any] | None = None,
    ) -> JeParams:
        ov = dict(overrides or {})
        unknown = set(ov) - set(PARAM_RULES)
        if unknown:
            raise JeTestError("Unknown JE parameter(s): " + ", ".join(sorted(unknown)) + ".")
        rules = _Rules(period_end)
        raw: dict[str, Any] = {}
        sources: dict[str, str] = {}
        for name, key in PARAM_RULES.items():
            if name in ov and ov[name] is not None:
                raw[name], sources[name] = ov[name], "override"
            elif key is not None:
                raw[name] = rules.value(key)
                sources[name] = rules.used[key]["ref"]
        tests = tuple(raw.get("tests") or TESTS)
        bad = [t for t in tests if t not in TESTS]
        if bad:
            raise JeTestError("Unknown JE test(s): " + ", ".join(bad) + ".")
        p = cls(
            period_end=period_end,
            round_multiple=Decimal(str(raw["round_multiple"])),
            round_min=Decimal(str(raw["round_min"])),
            period_end_days=int(raw["period_end_days"]),
            rare_user_max_pct=Decimal(str(raw["rare_user_max_pct"])),
            vague_keywords=tuple(_norm(k) for k in raw["vague_keywords"]),
            account_pair_min_count=int(raw["account_pair_min_count"]),
            score_test=int(raw["score_test"]),
            score_judgement=int(raw["score_judgement"]),
            judgement_min_items=int(raw["judgement_min_items"]),
            manual_voucher_prefixes=tuple(str(x).upper() for x in raw["manual_voucher_prefixes"]),
            sensitive_account_types=tuple(str(x).lower() for x in raw["sensitive_account_types"]),
            sensitive_account_codes=tuple(str(x) for x in raw["sensitive_account_codes"]),
            senior_users=tuple(str(x).upper() for x in raw.get("senior_users") or ()),
            large_amount=Decimal(str(raw["large_amount"])) if raw.get("large_amount") else None,
            tests=tests,
            sources=sources,
            rules_used=rules.used,
        )
        if p.round_multiple <= 0 or p.period_end_days < 0 or p.score_test < 1:
            raise JeTestError("JE parameters must be positive.")
        return p

    def as_dict(self) -> dict[str, Any]:
        return {
            "period_end": self.period_end,
            "round_multiple": self.round_multiple,
            "round_min": self.round_min,
            "period_end_days": self.period_end_days,
            "rare_user_max_pct": self.rare_user_max_pct,
            "vague_keywords": list(self.vague_keywords),
            "account_pair_min_count": self.account_pair_min_count,
            "score_test": self.score_test,
            "score_judgement": self.score_judgement,
            "judgement_min_items": self.judgement_min_items,
            "manual_voucher_prefixes": list(self.manual_voucher_prefixes),
            "sensitive_account_types": list(self.sensitive_account_types),
            "sensitive_account_codes": list(self.sensitive_account_codes),
            "senior_users": list(self.senior_users),
            "large_amount": self.large_amount,
            "tests": list(self.tests),
            "sources": self.sources,
        }


_PUNCT = re.compile(r"[^\w\s]")


def _norm(text: Any) -> str:
    return " ".join(_PUNCT.sub(" ", str(text or "").lower()).split())


def _time(v: Any) -> time | None:
    if isinstance(v, time):
        return v
    s = str(v or "").strip()
    m = re.fullmatch(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", s)
    if not m:
        return None
    hh, mm, ss = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
    if hh > 23 or mm > 59 or ss > 59:
        return None
    return time(hh, mm, ss)


@dataclass
class _Line:
    idx: int
    row_no: int
    ref: str
    voucher: str
    day: date | None
    at: time | None
    user: str
    account_code: str
    account_type: str
    narration: str
    party: str
    invoice: str
    debit: Decimal
    credit: Decimal
    flags: dict[str, str] = field(default_factory=dict)
    related: str | None = None

    @property
    def amount(self) -> Decimal:
        return self.debit if self.debit else self.credit

    @property
    def side(self) -> str:
        return "DR" if self.debit else "CR"

    @property
    def order(self) -> tuple[date, time, int]:
        return (self.day or date.min, self.at or time.min, self.row_no)


JE_COLUMNS = ("row_no", "line_id", "voucher_no", "posting_date", "entry_date", "posting_time",
              "user_id", "account_code", "account_type", "narration", "party_id",
              "invoice_no", "debit", "credit")


def _lines(rows: Iterable[Mapping[str, Any]]) -> list[_Line]:
    out = []
    for i, r in enumerate(rows):
        out.append(
            _Line(
                idx=i,
                row_no=int(r.get("row_no") or i + 1),
                ref=str(r.get("line_id") or r.get("row_no") or i + 1),
                voucher=str(r.get("voucher_no") or ""),
                day=r.get("posting_date") or r.get("entry_date"),
                at=_time(r.get("posting_time")),
                user=str(r.get("user_id") or "").strip(),
                account_code=str(r.get("account_code") or "").strip(),
                account_type=str(r.get("account_type") or "").strip(),
                narration=str(r.get("narration") or ""),
                party=str(r.get("party_id") or "").strip().upper(),
                invoice=str(r.get("invoice_no") or "").strip().upper(),
                debit=abs(Decimal(r.get("debit") or 0)),
                credit=abs(Decimal(r.get("credit") or 0)),
            )
        )
    return out


def _prefix(voucher: str) -> str:
    return re.split(r"[-/ ]", voucher, maxsplit=1)[0].upper()


def _sequence_gaps(lines: list[_Line]) -> list[dict[str, Any]]:
    nums: dict[str, set[int]] = defaultdict(set)
    for ln in lines:
        m = re.fullmatch(r"(.*?)(\d+)", ln.voucher)
        if m:
            nums[m.group(1)].add(int(m.group(2)))
    gaps = []
    for series, ns in sorted(nums.items()):
        missing = sorted(set(range(min(ns), max(ns) + 1)) - ns)
        if missing:
            gaps.append(
                {"series": series, "missing_count": len(missing), "first_missing": missing[:10]}
            )
    return gaps


def _duplicates(lines: list[_Line], key_fn: Any, code: str, describe: Any) -> None:
    groups: dict[Any, list[_Line]] = defaultdict(list)
    for ln in lines:
        k = key_fn(ln)
        if k is not None:
            groups[k].append(ln)
    for items in groups.values():
        vouchers = {ln.voucher for ln in items}
        if len(vouchers) < 2:
            continue
        items.sort(key=lambda x: x.order)
        first = items[0]
        for ln in items[1:]:
            if ln.voucher != first.voucher:
                ln.flags[code] = describe(ln, first)
                ln.related = ln.related or first.ref


def _calendar_of(
    cal: ResolvedCalendar | CalendarProfile, lines: list[_Line], period_end: date | None
) -> ResolvedCalendar:
    if isinstance(cal, ResolvedCalendar):
        return cal
    days = [ln.day for ln in lines if ln.day is not None]
    if period_end is not None:
        days += [period_end - timedelta(days=364), period_end]
    if not days:
        days = [date.today()]
    return ResolvedCalendar(cal, min(days), max(days))


def run_je_tests(
    rows: Iterable[Mapping[str, Any]],
    params: JeParams,
    calendar: ResolvedCalendar | CalendarProfile,
    *,
    dataset_hash: str | None = None,
) -> dict[str, Any]:
    lines = _lines(rows)
    if not lines:
        raise JeTestError("The dataset has no lines to test.")
    cal = _calendar_of(calendar, lines, params.period_end)
    on = set(params.tests)
    vouchers: dict[str, list[_Line]] = defaultdict(list)
    for ln in lines:
        vouchers[ln.voucher].append(ln)
    users: Counter[str] = Counter()  # vouchers per user
    for vl in vouchers.values():
        for u in {ln.user for ln in vl}:
            users[u] += 1
    n_vouchers = len(vouchers)
    rare = {
        u
        for u, c in users.items()
        if u and Decimal(c) / Decimal(n_vouchers) < params.rare_user_max_pct
    }
    pairs: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {}
    for v, vl in vouchers.items():
        pairs[v] = (
            tuple(sorted({ln.account_code for ln in vl if ln.debit})),
            tuple(sorted({ln.account_code for ln in vl if not ln.debit})),
        )
    pair_count = Counter(pairs.values())
    unbalanced = {
        v for v, vl in vouchers.items() if sum(ln.debit for ln in vl) != sum(ln.credit for ln in vl)
    }
    no_date = 0
    calendar_errors: set[str] = set()
    for ln in lines:
        f = ln.flags
        if ln.day is None:
            no_date += 1
        else:
            try:
                st = cal.status(ln.day)
            except CalendarError as exc:
                calendar_errors.add(str(exc))
                st = None
            if st is not None and "non_working_day" in on and not st.is_working:
                label = {
                    "weekend": "weekly off day",
                    "holiday": f"holiday ({st.holiday_name})",
                    "company_closure": "company closure",
                }[st.reason]
                f["non_working_day"] = f"{ln.day.strftime('%A')} {ln.day.isoformat()} - {label}" + (
                    " [provisional]" if st.provisional else ""
                )
                f["_reason"] = st.reason
            if (
                st is not None
                and "after_half_day_cutoff" in on
                and st.half_day_cutoff
                and ln.at is not None
                and ln.at > st.half_day_cutoff
            ):
                f["after_half_day_cutoff"] = (
                    f"{ln.day.strftime('%A')} {ln.day.isoformat()} at {ln.at.strftime('%H:%M')}"
                    f" - after the {st.half_day_cutoff.strftime('%H:%M')} half-day cut-off"
                )
            if (
                "period_end" in on
                and params.period_end is not None
                and abs((ln.day - params.period_end).days) <= params.period_end_days
            ):
                f["period_end"] = (
                    f"{ln.day.isoformat()} within {params.period_end_days} days"
                    f" of period end {params.period_end.isoformat()}"
                )
        amt = ln.amount
        if (
            "round_sum" in on
            and amt >= params.round_min
            and amt != 0
            and amt % params.round_multiple == 0
        ):
            f["round_sum"] = (
                f"AED {money(amt)} - multiple of {money(params.round_multiple)}"
                f" and >= {money(params.round_min)}"
            )
        if "rare_user" in on and ln.user in rare:
            f["rare_user"] = (
                f"User {ln.user} posted {users[ln.user]} of {n_vouchers} "
                f"vouchers (< {params.rare_user_max_pct * 100:.0f}%)"
            )
        if "senior_user" in on and ln.user.upper() in params.senior_users:
            f["senior_user"] = f"Posted by {ln.user} (senior management / IT user list)"
        if "large_amount" in on and params.large_amount is not None and amt >= params.large_amount:
            f["large_amount"] = f"AED {money(amt)} >= PM {money(params.large_amount)}"
        if "vague_narration" in on:
            nn = _norm(ln.narration)
            if not nn:
                f["vague_narration"] = "Blank narration"
            elif nn in params.vague_keywords:
                f["vague_narration"] = f"Vague narration: '{ln.narration.strip()}'"
        if (
            "manual_sensitive" in on
            and _prefix(ln.voucher) in params.manual_voucher_prefixes
            and (
                ln.account_type.lower() in params.sensitive_account_types
                or ln.account_code in params.sensitive_account_codes
            )
        ):
            f["manual_sensitive"] = (
                f"Manual voucher {ln.voucher} to {ln.account_code} ({ln.account_type})"
            )
        if (
            "unusual_account_pair" in on
            and pair_count[pairs[ln.voucher]] < params.account_pair_min_count
        ):
            dr, cr = pairs[ln.voucher]
            f["unusual_account_pair"] = (
                f"Dr {'/'.join(dr) or '-'} Cr {'/'.join(cr) or '-'} used"
                f" in {pair_count[pairs[ln.voucher]]} voucher(s)"
            )
        if "unbalanced_voucher" in on and ln.voucher in unbalanced:
            f["unbalanced_voucher"] = f"Voucher {ln.voucher} does not balance"
    if "duplicate_invoice" in on:
        _duplicates(
            lines,
            lambda x: (x.party, x.invoice, x.side) if x.party and x.invoice else None,
            "duplicate_invoice",
            lambda ln, first: (
                f"Invoice {ln.invoice} from {ln.party} already posted on "
                f"{first.day.isoformat() if first.day else '?'} ({first.voucher})"
            ),
        )
    if "duplicate_party_amount_date" in on:
        _duplicates(
            lines,
            lambda x: (
                (x.party, x.amount, x.day, x.side) if x.party and x.day and x.amount else None
            ),
            "duplicate_party_amount_date",
            lambda ln, first: (
                f"{ln.party} AED {money(ln.amount)} on "
                f"{ln.day.isoformat() if ln.day else '?'} also in {first.voucher}"
            ),
        )
    return _assemble(
        lines,
        params,
        cal,
        dataset_hash,
        n_vouchers,
        no_date,
        sorted(calendar_errors),
        _sequence_gaps(lines),
    )


def _assemble(
    lines: list[_Line],
    params: JeParams,
    cal: ResolvedCalendar,
    dataset_hash: str | None,
    n_vouchers: int,
    no_date: int,
    calendar_errors: list[str],
    gaps: list[dict[str, Any]],
) -> dict[str, Any]:
    flagged = []
    for ln in lines:
        reason = ln.flags.pop("_reason", None)
        if not ln.flags:
            continue
        flagged.append((ln, reason))
    for ln, _ in flagged:
        score = len(ln.flags)
        ln.__dict__["score"] = score
        ln.__dict__["selection"] = (
            "test"
            if score >= params.score_test
            else "judgement"
            if score >= params.score_judgement
            else ""
        )
    tested = sum(1 for ln, _ in flagged if ln.__dict__["selection"] == "test")
    if tested < params.judgement_min_items:
        pool = sorted(
            (ln for ln, _ in flagged if ln.__dict__["selection"] == "judgement"),
            key=lambda x: (-x.amount, x.row_no),
        )
        for ln in pool[: params.judgement_min_items - tested]:
            ln.__dict__["selection"] = "test_topup"
    summary = []
    for code in TESTS:
        hit = [ln for ln, _ in flagged if code in ln.flags]
        summary.append(
            {
                "test": code,
                "title": TESTS[code],
                "enabled": code in params.tests,
                "lines": len(hit),
                "vouchers": len({ln.voucher for ln in hit}),
                "value": money(sum((ln.amount for ln in hit), Decimal(0))),
            }
        )
    items = [
        {
            "line_ref": ln.ref,
            "row_no": ln.row_no,
            "voucher_no": ln.voucher,
            "date": ln.day,
            "time": ln.at.strftime("%H:%M:%S") if ln.at else None,
            "user_id": ln.user,
            "account_code": ln.account_code,
            "amount": ln.amount,
            "side": ln.side,
            "flags": list(ln.flags),
            "details": dict(ln.flags),
            "non_working_reason": reason,
            "related_line": ln.related,
            "risk_score": ln.__dict__["score"],
            "selection": ln.__dict__["selection"],
        }
        for ln, reason in sorted(flagged, key=lambda t: (-t[0].__dict__["score"], t[0].row_no))
    ]
    dist = Counter(i["risk_score"] for i in items)
    selected = [i for i in items if i["selection"] in ("test", "test_topup")]
    return {
        "engine_version": f"{ENGINE_NAME} {ENGINE_VERSION}",
        "dataset_hash": dataset_hash,
        "parameters": params.as_dict(),
        "calendar_hash": cal.hash,
        "calendar": cal.summary(),
        "calendar_errors": calendar_errors,
        "population": {"lines": len(lines), "vouchers": n_vouchers, "lines_without_date": no_date},
        "summary": summary,
        "flagged_lines": len(items),
        "score_distribution": {str(k): dist[k] for k in sorted(dist)},
        "selected_for_testing": len(selected),
        "selected_value": money(sum((i["amount"] for i in selected), Decimal(0))),
        "sequence_gaps": gaps,
        "flags": items,
        "rule_versions_used": params.rules_used,
        "rules_pending_verification": any(
            v["status"] != "approved" for v in params.rules_used.values()
        ),
        "selection_basis": (
            f"Score = number of criteria met. Score >= {params.score_test}: "
            f"test all; score {params.score_judgement}: judgement; minimum "
            f"{params.judgement_min_items} items. Never random."
        ),
    }


# ------------------------------------------------------------------ persistence + job
def start_je_run(
    dataset_id: str, overrides: Mapping[str, Any] | None, *, user_id: str | None
) -> tuple[str, str]:
    """Create a JeRun and submit the background job; returns (je_run_id, job_id)."""
    from app.core.db import session_factory
    from app.models import Engagement, JeRun
    from app.services.datasets import assert_usable

    ds = assert_usable(dataset_id)
    with session_factory()() as s:
        eng = s.get(Engagement, ds.engagement_id)
        period_end = eng.fye if eng is not None else None
    params = JeParams.build(period_end, overrides)  # validate before queueing
    with session_factory()() as s:
        run = JeRun(
            engagement_id=ds.engagement_id,
            dataset_id=ds.id,
            parameters=jsonable(params.as_dict()),
            engine_version=ENGINE_VERSION,
            status="queued",
            created_by=user_id,
        )
        s.add(run)
        s.commit()
        run_id = run.id

    job_id = jobs.enqueue("je_tests", {"run_id": run_id, "overrides": dict(overrides or {})},
                          engagement_id=ds.engagement_id, created_by=user_id)
    with session_factory()() as s:
        r = s.get(JeRun, run_id)
        if r is not None and r.job_id is None:
            r.job_id = job_id
            s.commit()
    return run_id, job_id


@jobs.task("je_tests")
def je_task(job_id: str, *, run_id: str, overrides: dict[str, Any]) -> str:
    from app.core.db import session_factory
    from app.models import JeRun

    try:
        _execute(run_id, job_id, dict(overrides))
    except Exception as exc:
        with session_factory()() as s2:
            r = s2.get(JeRun, run_id)
            if r is not None:
                r.status = "cancelled" if isinstance(exc, jobs.JobCancelled) else "failed"
                s2.commit()
        raise
    return f"je_run:{run_id}"


def _execute(run_id: str, job_id: str, overrides: dict[str, Any]) -> None:
    from pathlib import Path

    from sqlalchemy import update

    from app.core.db import session_factory
    from app.models import Dataset, Engagement, JeFlag, JeRun
    from app.services.benford import BenfordError, run_benford
    from app.services.calendar import resolve_engagement
    from app.services.importer import read_parquet_rows

    with session_factory()() as s:
        run = s.get(JeRun, run_id)
        assert run is not None
        ds = s.get(Dataset, run.dataset_id)
        eng = s.get(Engagement, run.engagement_id)
        assert ds is not None and eng is not None
        path, sha, eng_id, fye = Path(ds.parquet_ref or ""), ds.sha256, eng.id, eng.fye
    jobs.set_progress(job_id, 10)
    # Large files (3.11): stream projected columns; never hold the whole file as dicts.
    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    dates = pq.read_table(path, columns=["posting_date", "entry_date"])
    days = [d for d in (pc.min(pc.coalesce(dates["posting_date"], dates["entry_date"])).as_py(),
                        pc.max(pc.coalesce(dates["posting_date"], dates["entry_date"])).as_py())
            if d is not None]
    del dates
    start = min([*days, fye - timedelta(days=364)])
    end = max([*days, fye])
    cal = resolve_engagement(eng_id, start, end)
    params = JeParams.build(fye, overrides)
    jobs.set_progress(job_id, 40)
    res = run_je_tests(read_parquet_rows(path, columns=JE_COLUMNS), params, cal,
                       dataset_hash=sha)
    try:
        res["benford"] = run_benford(
            (r.get("debit") or r.get("credit") or Decimal(0)
             for r in read_parquet_rows(path, columns=("debit", "credit"))), on_date=fye
        )
    except BenfordError as exc:  # pragma: no cover - only when every amount is < 10
        res["benford"] = {"error": str(exc)}
    jobs.set_progress(job_id, 80)
    res.update(
        {
            "je_run_id": run_id,
            "dataset_id": run.dataset_id,
            "engagement_id": eng_id,
            "job_id": job_id,
        }
    )
    out = jsonable(res)
    with session_factory()() as s:
        s.execute(
            update(JeRun)
            .where(
                JeRun.engagement_id == eng_id,
                JeRun.dataset_id == run.dataset_id,
                JeRun.id != run_id,
                JeRun.status == "current",
            )
            .values(status="superseded")
        )
        r = s.get(JeRun, run_id)
        assert r is not None
        r.calendar_hash = res["calendar_hash"]
        r.rule_versions_used = out["rule_versions_used"]
        r.parameters = out["parameters"]
        r.result = out
        r.status = "current"
        for it in res["flags"]:
            s.add(
                JeFlag(
                    je_run_id=run_id,
                    line_ref=it["line_ref"],
                    flags=it["flags"],
                    risk_score=it["risk_score"],
                )
            )
        s.commit()


def get_je_run(run_id: str) -> tuple[str, dict[str, Any]]:
    from app.core.db import session_factory
    from app.models import JeRun

    with session_factory()() as s:
        run = s.get(JeRun, run_id)
        if run is None:
            raise JeTestError("JE run not found.")
        base = {
            "je_run_id": run.id,
            "status": run.status,
            "job_id": run.job_id,
            "dataset_id": run.dataset_id,
            "engagement_id": run.engagement_id,
        }
        return run.engagement_id, {**(run.result or {}), **base}


def list_flags(run_id: str, *, flag: str | None = None, min_score: int = 0, offset: int = 0,
               limit: int = 100) -> tuple[str, int, list[dict[str, Any]]]:
    """Paginated flagged lines of a run, highest risk first (prompt 3.11)."""
    from sqlalchemy import String, cast, func, select

    from app.core.db import session_factory
    from app.models import JeFlag, JeRun

    with session_factory()() as s:
        run = s.get(JeRun, run_id)
        if run is None:
            raise JeTestError("JE run not found.")
        q = select(JeFlag).where(JeFlag.je_run_id == run_id, JeFlag.risk_score >= min_score)
        if flag:
            q = q.where(cast(JeFlag.flags, String).like(
                '%"' + flag.replace("_", r"\_") + '"%', escape="\\"))
        total = s.execute(select(func.count()).select_from(q.subquery())).scalar_one()
        items = s.execute(q.order_by(JeFlag.risk_score.desc(), JeFlag.id).offset(offset)
                          .limit(limit)).scalars()
        return run.engagement_id, int(total), [
            {"line_ref": f.line_ref, "flags": list(f.flags), "risk_score": f.risk_score}
            for f in items]
