"""Sampling (ISA 530) – prompt 3.3.

Methods: MUS, simple random, systematic, stratified, and key items + MUS.

- All money is Decimal. No float enters a result, except the uniform draw from
  ``numpy.random.default_rng(seed)``, which is converted at once to Decimal.
- Confidence factors, expansion factors and limits come from the Rules Library
  (``rules.get_rule``) for the engagement's period end. Every result records the rule
  versions used.
- Sample size defaults to the firm formula (firm_methodology_v0.2 §5):
  ``n = ROUNDUP(Pop × CF / (TM − Exp × EF), 0)`` with Exp = 10% of TM.
  The Build Guide formula ``n = ceil(Pop × CF / TM)`` is available as ``size_formula="guide"``
  (plans/DECISIONS.md D1).
- No AI is involved anywhere in this module.
"""

from __future__ import annotations

import secrets
from bisect import bisect_left
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_CEILING, ROUND_DOWN, ROUND_FLOOR, ROUND_HALF_UP, Decimal
from typing import Any, Literal

import numpy as np

from app.services.rules import Rule, RuleNotFound, get_rule
from app.version import ENGINE_NAME, ENGINE_VERSION

IMPLEMENTED_BY_PROMPT = "3.3"

Method = Literal["mus", "random", "systematic", "stratified", "key_items_mus"]
Basis = Literal["debit", "credit", "signed", "absolute"]
SizeFormula = Literal["firm", "guide"]

CENT = Decimal("0.01")
START_QUANT = CENT  # D7: random start truncated to fils, always in [0, J)
ZERO = Decimal("0")
MAX_SEED = 2**31 - 1


class SamplingError(ValueError):
    """A request that cannot be sampled; the message is shown to the user as is."""


# ------------------------------------------------------------------ formatting helpers
def money(v: Decimal) -> str:
    """12553004.07 -> '12,553,004.07' (ROUND_HALF_UP, 2 dp)."""
    return f"{v.quantize(CENT, ROUND_HALF_UP):,.2f}"


def q2(v: Decimal) -> Decimal:
    return v.quantize(CENT, ROUND_HALF_UP)


def _dec(v: Any) -> Decimal:
    return v if isinstance(v, Decimal) else Decimal(str(v))


# ------------------------------------------------------------------ population
@dataclass(frozen=True)
class PopItem:
    row_no: int
    line_id: str
    value: Decimal
    account_code: str = ""
    attrs: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"row_no": self.row_no, "line_id": self.line_id, "value": q2(self.value),
                "account_code": self.account_code}


@dataclass
class Population:
    items: list[PopItem]
    excluded: list[PopItem]  # credit / negative lines, listed, never silently dropped
    zero_lines: int
    basis: str
    filter_text: str

    @property
    def value(self) -> Decimal:
        return sum((i.value for i in self.items), ZERO)

    @property
    def count(self) -> int:
        return len(self.items)

    def summary(self) -> dict[str, Any]:
        return {"value": q2(self.value), "count": self.count, "basis": self.basis,
                "filter": self.filter_text, "zero_lines_excluded": self.zero_lines}


def _match_code(code: str, patterns: Sequence[str]) -> bool:
    for p in patterns:
        if p.endswith("*") and code.startswith(p[:-1]):
            return True
        if code == p:
            return True
    return False


def build_population(rows: Iterable[Mapping[str, Any]], *, basis: Basis = "debit",
                     account_types: Sequence[str] | None = None,
                     account_codes: Sequence[str] | None = None) -> Population:
    """Select the test population from parsed GL rows (in file order).

    basis:
      debit    – value = debit; lines with only a credit are excluded and listed.
      credit   – value = credit; lines with only a debit are excluded and listed.
      signed   – value = debit − credit; negative lines are excluded and listed.
      absolute – value = |debit − credit|; nothing is excluded except zero lines.
    """
    types = {t.strip().lower() for t in account_types or [] if t.strip()}
    codes = [c.strip() for c in account_codes or [] if c.strip()]
    items: list[PopItem] = []
    excluded: list[PopItem] = []
    zero = 0
    for r in rows:
        if types and str(r.get("account_type") or "").strip().lower() not in types:
            continue
        code = str(r.get("account_code") or "")
        if codes and not _match_code(code, codes):
            continue
        dr, cr = r.get("debit") or ZERO, r.get("credit") or ZERO
        if basis == "debit":
            value, other = dr, cr
        elif basis == "credit":
            value, other = cr, dr
        elif basis == "signed":
            value = dr - cr
            other = -value if value < 0 else ZERO
        else:
            value, other = abs(dr - cr), ZERO
        item = PopItem(int(r["row_no"]), str(r.get("line_id") or ""), value, code)
        if value > 0:
            items.append(item)
        elif other > 0:
            excluded.append(PopItem(item.row_no, item.line_id, other, code))
        else:
            zero += 1
    parts = []
    if types:
        parts.append("account_type in (" + ", ".join(sorted(types)) + ")")
    if codes:
        parts.append("account_code in (" + ", ".join(codes) + ")")
    parts.append({"debit": "debit > 0", "credit": "credit > 0", "signed": "debit - credit > 0",
                  "absolute": "|debit - credit| > 0"}[basis])
    return Population(items, excluded, zero, basis, " and ".join(parts))


# ------------------------------------------------------------------ rules
@dataclass
class RuleSet:
    on_date: date | None
    used: dict[str, dict[str, Any]] = field(default_factory=dict)

    def get(self, key: str) -> Rule:
        try:
            r = get_rule(key, self.on_date)
        except RuleNotFound:
            raise SamplingError(
                f"The Rules Library has no value for '{key}' on {self.on_date}. Ask the "
                "methodology owner to add it before running this step.") from None
        self.used[key] = {"version": r.version, "value": r.value, "status": r.status,
                          "ref": r.ref}
        return r

    @property
    def pending(self) -> bool:
        return any(v["status"] != "approved" for v in self.used.values())


def _level_key(level: str | int) -> str:
    s = str(level).strip().rstrip("%")
    if s not in {"80", "90", "95", "99"}:
        raise SamplingError("Confidence level must be 80, 90, 95 or 99 percent.")
    return s


# ------------------------------------------------------------------ MUS
@dataclass
class MusSize:
    n: int
    interval: Decimal
    cf: Decimal
    ef: Decimal | None
    expected: Decimal
    basic_precision: Decimal
    formula_text: str
    guide_n: int


def mus_size(pop_value: Decimal, tm: Decimal, level: str | int, rules: RuleSet, *,
             formula: SizeFormula = "firm", expected_pct: Decimal | None = None) -> MusSize:
    lv = _level_key(level)
    if tm <= 0:
        raise SamplingError("Tolerable misstatement must be greater than zero.")
    if pop_value <= 0:
        raise SamplingError("The test population has no value to sample.")
    cf = _dec(rules.get(f"sampling.mus.cf.{lv}").value)
    guide_n = int((pop_value * cf / tm).to_integral_value(ROUND_CEILING))
    if formula == "guide":
        n = guide_n
        text = f"n = ceil({money(pop_value)} x {cf:.2f} / {money(tm)}) = {n}"
        ef: Decimal | None = None
        expected = ZERO
    else:
        pct = expected_pct if expected_pct is not None else _dec(
            rules.get("sampling.mus.expected_pct").value)
        max_pct = _dec(rules.get("sampling.mus.max_expected_pct").value)
        if pct < 0:
            raise SamplingError("Expected misstatement cannot be negative.")
        if pct > max_pct:
            raise SamplingError(
                f"Expected misstatement is {pct:.0%} of TM, above the {max_pct:.0%} limit. "
                "Do not sample: use a substantive approach for this population.")
        expected = tm * pct
        ef = _dec(rules.get(f"sampling.mus.ef.{lv}").value) if expected > 0 else None
        denom = tm - expected * (ef or ZERO)
        if denom <= 0:  # pragma: no cover - needs Exp x EF >= TM, blocked by the 50% cap
            raise SamplingError("TM minus expected misstatement x EF is not positive; reduce "
                                "the expected misstatement.")
        n = int((pop_value * cf / denom).to_integral_value(ROUND_CEILING))
        if ef is None:
            text = f"n = ROUNDUP({money(pop_value)} x {cf:.2f} / {money(tm)}, 0) = {n}"
        else:
            text = (f"n = ROUNDUP({money(pop_value)} x {cf:.2f} / ({money(tm)} - "
                    f"{money(expected)} x {ef}), 0) = {n}")
    interval = pop_value / n
    text += f"; J = {money(interval)}"
    return MusSize(n, interval, cf, ef, expected, cf * interval, text, guide_n)


def random_start(rng: np.random.Generator, interval: Decimal) -> Decimal:
    u = Decimal(repr(float(rng.random())))
    return (u * interval).quantize(START_QUANT, ROUND_DOWN)


@dataclass
class Selected:
    item: PopItem
    hits: int = 0
    points: list[Decimal] = field(default_factory=list)
    top_stratum: bool = False
    stratum: int | None = None
    key_item: bool = False

    def as_dict(self) -> dict[str, Any]:
        d = self.item.as_dict()
        d.update({"top_stratum": self.top_stratum, "key_item": self.key_item,
                  "hits": self.hits, "selection_points": [q2(p) for p in self.points],
                  "stratum": self.stratum})
        return d


def mus_select(items: Sequence[PopItem], n: int, interval: Decimal, start: Decimal
               ) -> list[Selected]:
    """Select the first line whose cumulative value ≥ start + k·J, for k = 0 … n−1."""
    cum: list[Decimal] = []
    running = ZERO
    for it in items:
        running += it.value
        cum.append(running)
    chosen: dict[int, Selected] = {}
    for k in range(n):
        point = start + k * interval
        idx = bisect_left(cum, point)
        if idx >= len(items):  # pragma: no cover - start < J guarantees the last point fits
            idx = len(items) - 1
        sel = chosen.setdefault(idx, Selected(items[idx]))
        sel.hits += 1
        sel.points.append(point)
    out = [chosen[i] for i in sorted(chosen)]
    for s in out:
        s.top_stratum = s.item.value >= interval
    return out


# ------------------------------------------------------------------ other methods
def random_select(items: Sequence[PopItem], n: int, rng: np.random.Generator) -> list[Selected]:
    if n > len(items):
        raise SamplingError(f"Sample size {n} is larger than the population ({len(items)} "
                            "lines). Test the whole population instead.")
    idx = sorted(int(i) for i in rng.choice(len(items), size=n, replace=False))
    return [Selected(items[i], hits=1) for i in idx]


def systematic_select(items: Sequence[PopItem], n: int, rng: np.random.Generator
                      ) -> tuple[list[Selected], Decimal, Decimal]:
    if n > len(items):
        raise SamplingError(f"Sample size {n} is larger than the population ({len(items)} "
                            "lines). Test the whole population instead.")
    step = Decimal(len(items)) / n
    start = Decimal(repr(float(rng.random()))) * step
    idx = [int((start + k * step).to_integral_value(ROUND_FLOOR)) for k in range(n)]
    return [Selected(items[i], hits=1) for i in idx], step, start


@dataclass
class Stratum:
    number: int
    lower: Decimal
    upper: Decimal | None
    items: list[PopItem]
    allocated: int = 0

    @property
    def value(self) -> Decimal:
        return sum((i.value for i in self.items), ZERO)

    def as_dict(self) -> dict[str, Any]:
        return {"stratum": self.number, "lower": q2(self.lower),
                "upper": q2(self.upper) if self.upper is not None else None,
                "count": len(self.items), "value": q2(self.value), "sample_size": self.allocated}


def make_strata(items: Sequence[PopItem], *, boundaries: Sequence[Decimal] | None = None,
                num_strata: int | None = None) -> list[Stratum]:
    """User boundaries (upper bounds, ascending) or quantile strata of equal line count.

    Each line falls in exactly one stratum: lower ≤ value < upper (last stratum open).
    """
    if boundaries:
        bounds = sorted({_dec(b) for b in boundaries})
    else:
        k = 3 if num_strata is None else num_strata
        if k < 1:
            raise SamplingError("Number of strata must be at least 1.")
        values = sorted(i.value for i in items)
        bounds = sorted({values[(len(values) * j) // k] for j in range(1, k)}) if values else []
    edges: list[Decimal | None] = [*bounds, None]
    strata: list[Stratum] = []
    lower = ZERO
    for num, up in enumerate(edges, 1):
        strata.append(Stratum(num, lower, up, []))
        lower = up if up is not None else lower
    for it in items:
        pos = bisect_left(bounds, it.value)
        if pos < len(bounds) and it.value == bounds[pos]:
            pos += 1
        strata[pos].items.append(it)
    return [s for s in strata if s.items]


def allocate(strata: Sequence[Stratum], n: int) -> None:
    """Value-proportional allocation, minimum 1 per stratum, capped at the stratum size
    (largest-remainder rounding, so the allocations sum to max(n, number of strata))."""
    total = sum((s.value for s in strata), ZERO)
    target = max(n, len(strata))
    capacity = sum(len(s.items) for s in strata)
    target = min(target, capacity)
    for s in strata:
        s.allocated = 1
    remaining = target - len(strata)
    while remaining > 0:
        open_ = [s for s in strata if s.allocated < len(s.items)]
        open_value = sum((s.value for s in open_), ZERO) or total
        shares = [(s, s.value / open_value * remaining) for s in open_]
        floors = {s.number: min(int(sh.to_integral_value(ROUND_FLOOR)),
                                len(s.items) - s.allocated) for s, sh in shares}
        given = sum(floors.values())
        for s, _ in shares:
            s.allocated += floors[s.number]
        left = remaining - given
        ranked = sorted(shares, key=lambda t: (-(t[1] - t[1].to_integral_value(ROUND_FLOOR)),
                                               t[0].number))
        for s, _ in ranked:
            if left == 0:
                break
            if s.allocated < len(s.items):
                s.allocated += 1
                left -= 1
        remaining = left


def stratified_select(items: Sequence[PopItem], n: int, rng: np.random.Generator, *,
                      boundaries: Sequence[Decimal] | None, num_strata: int | None
                      ) -> tuple[list[Selected], list[Stratum]]:
    strata = make_strata(items, boundaries=boundaries, num_strata=num_strata)
    allocate(strata, n)
    picked: list[Selected] = []
    for s in strata:
        idx = sorted(int(i) for i in rng.choice(len(s.items), size=s.allocated, replace=False))
        picked += [Selected(s.items[i], hits=1, stratum=s.number) for i in idx]
    picked.sort(key=lambda x: x.item.row_no)
    return picked, strata


# ------------------------------------------------------------------ orchestration
@dataclass
class SampleRequest:
    method: Method = "mus"
    basis: Basis = "debit"
    account_types: list[str] = field(default_factory=list)
    account_codes: list[str] = field(default_factory=list)
    confidence: str = "95"
    tolerable_misstatement: Decimal | None = None
    expected_misstatement_pct: Decimal | None = None
    size_formula: SizeFormula = "firm"
    sample_size: int | None = None
    key_item_threshold: Decimal | None = None
    strata_boundaries: list[Decimal] | None = None
    num_strata: int | None = None
    seed: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {k: (str(v) if isinstance(v, Decimal) else
                    [str(x) for x in v] if isinstance(v, list) and v and isinstance(v[0], Decimal)
                    else v) for k, v in self.__dict__.items()}


def _rationale(req: SampleRequest, res: dict[str, Any], pop: Population) -> str:
    pv = money(pop.value)
    excl = res["credit_lines_excluded"]
    excl_text = (f" {excl['count']} credit/negative line(s) totalling AED {money(excl['value'])} "
                 "were excluded from the sampling population and are listed separately for "
                 "consideration." if excl["count"] else "")
    seed = f" The selection is reproducible with seed {res['seed']}."
    if res["status"] == "no_sampling":
        return (f"The calculated sample size for the population of AED {pv} "
                f"({pop.count} lines; {pop.filter_text}) is {res['n_required']}, below the "
                f"firm minimum of {res['min_n']}. Statistical sampling is not used; the items "
                "are tested by other substantive procedures." + excl_text)
    if req.method in ("mus", "key_items_mus"):
        key = ""
        if req.method == "key_items_mus":
            k = res["key_items"]
            key = (f" {k['count']} key item(s) at or above AED "
                   f"{money(_dec(req.key_item_threshold))} (total AED {money(k['value'])}) "
                   "were removed and tested 100% before sampling the remainder.")
        ts = res["top_stratum"]
        if res["random_start"] is None:
            mus = (" The remaining population was not sampled statistically: "
                   + (f"{res['formula_text']}, below the minimum of {res['min_n']}."
                      if res["formula_text"] else "no lines remain below the threshold."))
        else:
            mus = (f" At {req.confidence}% confidence (confidence factor {res['cf_value']}) and "
                   f"tolerable misstatement of AED {money(_dec(req.tolerable_misstatement))}, "
                   f"{res['formula_text']}. Items of AED {money(res['interval'])} or more form "
                   f"the top stratum ({ts['count']} item(s), AED {money(ts['value'])}) and are "
                   f"tested 100%. The sample was selected from a random start of AED "
                   f"{money(res['random_start'])} at a fixed interval.")
        return (f"Monetary unit sampling (ISA 530) was applied to the population of AED {pv} "
                f"({pop.count} lines; {pop.filter_text}).{key}{mus} {res['sample_size']} "
                f"distinct line(s) were selected in total." + excl_text + seed)
    label = {"random": "Simple random sampling without replacement",
             "systematic": "Systematic sampling from a random start at a fixed count interval",
             "stratified": "Stratified sampling with value-proportional allocation (minimum one "
                           "item per stratum)"}[req.method]
    return (f"{label} (ISA 530) was applied to the population of AED {pv} ({pop.count} lines; "
            f"{pop.filter_text}); {res['sample_size']} line(s) were selected."
            + excl_text + seed)


def run_sampling(rows: Iterable[Mapping[str, Any]], req: SampleRequest, *,
                 period_end: date | None, dataset_hash: str | None) -> dict[str, Any]:
    """Pure calculation: rows in, result dict out (Decimals kept as Decimal)."""
    rules = RuleSet(period_end)
    pop = build_population(rows, basis=req.basis, account_types=req.account_types,
                           account_codes=req.account_codes)
    seed = req.seed if req.seed is not None else secrets.randbelow(MAX_SEED)
    if not 0 <= seed <= MAX_SEED:
        raise SamplingError(f"Seed must be between 0 and {MAX_SEED}.")
    rng = np.random.default_rng(seed)
    min_n = int(rules.get("sampling.min_n").value)
    warn_pct = _dec(rules.get("sampling.size_difference_warn_pct").value)
    warnings: list[str] = []
    res: dict[str, Any] = {
        "method": req.method, "status": "selected", "parameters": req.as_dict(),
        "cf_value": None, "cf_rule_version": None, "ef_value": None, "formula_text": None,
        "n_required": None, "sample_size": 0, "interval": None, "basic_precision": None,
        "random_start": None, "seed": seed, "min_n": min_n, "population": pop.summary(),
        "top_stratum": {"count": 0, "value": ZERO, "items": []},
        "key_items": {"count": 0, "value": ZERO, "items": []},
        "credit_lines_excluded": {"count": len(pop.excluded),
                                  "value": q2(sum((i.value for i in pop.excluded), ZERO)),
                                  "items": [i.as_dict() for i in pop.excluded]},
        "strata": [], "items": [], "warnings": warnings,
        "engine_version": f"{ENGINE_NAME} {ENGINE_VERSION}", "dataset_hash": dataset_hash,
        "guide_formula_n": None,
    }
    if pop.count == 0:
        raise SamplingError("No lines match the population filter, so there is nothing to "
                            "sample. Check the account types or codes.")
    selected: list[Selected] = []
    if req.method in ("mus", "key_items_mus"):
        if req.tolerable_misstatement is None:
            raise SamplingError("Tolerable misstatement is required for MUS.")
        tm = _dec(req.tolerable_misstatement)
        mus_items = pop.items
        if req.method == "key_items_mus":
            if req.key_item_threshold is None or req.key_item_threshold <= 0:
                raise SamplingError("Key item threshold (AED) is required for key items + MUS.")
            thr = _dec(req.key_item_threshold)
            keys = [i for i in pop.items if i.value >= thr]
            mus_items = [i for i in pop.items if i.value < thr]
            key_sel = [Selected(i, key_item=True) for i in keys]
            res["key_items"] = {"count": len(keys), "value": q2(sum((i.value for i in keys), ZERO)),
                                "items": [s.as_dict() for s in key_sel]}
            selected += key_sel
        size = None
        if mus_items:
            remainder = sum((i.value for i in mus_items), ZERO)
            size = mus_size(remainder, tm, req.confidence, rules, formula=req.size_formula,
                            expected_pct=req.expected_misstatement_pct)
            res.update(cf_value=size.cf, ef_value=size.ef, formula_text=size.formula_text,
                       n_required=size.n, interval=size.interval,
                       basic_precision=size.basic_precision, guide_formula_n=size.guide_n,
                       cf_rule_version=rules.used[f"sampling.mus.cf.{_level_key(req.confidence)}"
                                                  ]["ref"])
        if size is not None and size.n < min_n:
            res["status"] = "no_sampling" if not selected else "selected"
            warnings.append(f"The calculated sample size is {size.n}, below the minimum of "
                            f"{min_n}: do not use statistical sampling for this population.")
        elif size is not None:
            start = random_start(rng, size.interval)
            res["random_start"] = start
            mus = mus_select(mus_items, size.n, size.interval, start)
            selected += mus
            top = [s for s in mus if s.top_stratum]
            res["top_stratum"] = {"count": len(top),
                                  "value": q2(sum((s.item.value for s in top), ZERO)),
                                  "items": [s.as_dict() for s in top]}
            if Decimal(size.n - len(mus)) > warn_pct * size.n:
                warnings.append(
                    f"{len(mus)} distinct lines will be tested against a calculated size of "
                    f"{size.n} ({size.n - len(mus)} selections fell on top-stratum lines "
                    "selected more than once). The difference is over "
                    f"{warn_pct:.0%}; document this on the working paper.")
    else:
        if req.sample_size is None or req.sample_size < 1:
            raise SamplingError("Sample size is required for random, systematic and "
                                "stratified sampling.")
        res["n_required"] = req.sample_size
        if req.method == "random":
            selected = random_select(pop.items, req.sample_size, rng)
        elif req.method == "systematic":
            selected, step, start = systematic_select(pop.items, req.sample_size, rng)
            res["interval"], res["random_start"] = step, start
            res["formula_text"] = (f"interval = {pop.count} lines / {req.sample_size} = "
                                   f"{step:.4f} lines; start = {start:.4f}")
        else:
            selected, strata = stratified_select(
                pop.items, req.sample_size, rng, boundaries=req.strata_boundaries,
                num_strata=req.num_strata)
            res["strata"] = [s.as_dict() for s in strata]
            res["formula_text"] = "; ".join(
                f"stratum {s.number}: {len(s.items)} lines, AED {money(s.value)} -> "
                f"{s.allocated}" for s in strata)
            if sum(s.allocated for s in strata) != req.sample_size:
                warnings.append(f"Allocation gives {sum(s.allocated for s in strata)} items "
                                f"(minimum one per stratum, capped at stratum size) against "
                                f"the requested {req.sample_size}.")
    res["items"] = [s.as_dict() for s in sorted(selected, key=lambda s: s.item.row_no)]
    res["sample_size"] = len(selected)
    res["rule_versions_used"] = rules.used
    res["rules_pending_verification"] = rules.pending
    if rules.pending:
        warnings.append("Rules used are pending verification (firm_methodology_v0.2 DRAFT); "
                        "results are not final until the Rules Library is approved.")
    res["rationale"] = _rationale(req, res, pop)
    return res


# ------------------------------------------------------------------ persistence
def jsonable(v: Any) -> Any:
    """Decimals become strings (never floats) so stored results keep exact values."""
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, dict):
        return {k: jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [jsonable(x) for x in v]
    return v


def create_sample(dataset_id: str, req: SampleRequest, *, user_id: str | None
                  ) -> dict[str, Any]:
    """Run sampling on a validated dataset and store Sample + SampleItems."""
    from pathlib import Path

    from app.core.db import session_factory
    from app.models import Engagement, Sample, SampleItem
    from app.services.datasets import assert_usable
    from app.services.importer import read_parquet_rows

    ds = assert_usable(dataset_id)
    with session_factory()() as s:
        eng = s.get(Engagement, ds.engagement_id)
        period_end = eng.fye if eng is not None else None
    if ds.parquet_ref is None:  # pragma: no cover - assert_usable guarantees a parsed file
        raise SamplingError("The dataset has not been read yet.")
    res = run_sampling(read_parquet_rows(Path(ds.parquet_ref)), req, period_end=period_end,
                       dataset_hash=ds.sha256)
    res["dataset_id"] = ds.id
    res["engagement_id"] = ds.engagement_id
    with session_factory()() as s:
        smp = Sample(engagement_id=ds.engagement_id, dataset_id=ds.id, method=req.method,
                     parameters=jsonable(req.as_dict()), cf_value=res["cf_value"],
                     formula_text=res["formula_text"], seed=res["seed"], file_hash=ds.sha256,
                     rule_versions_used=jsonable(res["rule_versions_used"]),
                     engine_version=ENGINE_VERSION, created_by=user_id)
        s.add(smp)
        s.flush()
        res["sample_id"] = smp.id
        for it in res["items"]:
            s.add(SampleItem(sample_id=smp.id, line_ref=it["line_id"] or str(it["row_no"]),
                             book_value=it["value"], top_stratum=it["top_stratum"],
                             attributes=jsonable({k: it[k] for k in (
                                 "row_no", "account_code", "hits", "selection_points",
                                 "stratum", "key_item")})))
        out = jsonable(res)
        smp.result = out
        s.commit()
    return dict(out)


def get_sample(sample_id: str) -> tuple[str, dict[str, Any]]:
    from app.core.db import session_factory
    from app.models import Sample

    with session_factory()() as s:
        smp = s.get(Sample, sample_id)
        if smp is None or smp.result is None:
            raise SamplingError("Sample not found.")
        return smp.engagement_id, dict(smp.result)
