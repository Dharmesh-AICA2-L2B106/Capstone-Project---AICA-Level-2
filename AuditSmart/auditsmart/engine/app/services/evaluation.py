"""Evaluation of sample results (ISA 450 / ISA 530), prompt 3.5.

MUS (classic, DECISIONS D2), as in golden_results.xlsx sheet "Projection":
- Top stratum (book >= J) and key items: the actual misstatement.
- Items < J: tainting = misstatement / book; projected = tainting x J.
- Basic precision BP = CF x J.
- Incremental allowance: overstatements < J ranked by projected value (descending; ties
  share a rank, like the sheet's COUNTIFS), IA = sum(projected x (factor - 1)), with the
  factors taken from the rule ``sampling.mus.if.<level>``.
- UML = BP + sum of projected (including the top-stratum actuals) + IA; conclusion UML <= TM.

Ratio projection (non-MUS samples, or ``method="ratio"``): misstatement / book ratio of
the sampled items x the population value they represent (per stratum when stratified),
plus key and top-stratum items at their actual value.

Arithmetic is exact Decimal; display values are rounded HALF_UP to 2 dp. No AI is involved.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from app.services.rules import RuleNotFound, get_rule
from app.services.sampling import money, q2
from app.version import ENGINE_NAME, ENGINE_VERSION

IMPLEMENTED_BY_PROMPT = "3.5"

ZERO = Decimal(0)
ONE = Decimal(1)
EvalMethod = Literal["mus", "ratio"]
ACCEPTABLE = "Acceptable"
EXCEEDS = "Exceeds - further work"


class EvaluationError(ValueError):
    pass


@dataclass(frozen=True)
class EvalItem:
    line_ref: str
    book: Decimal
    audited: Decimal
    top_stratum: bool = False  # recomputed for MUS as book >= J
    key_item: bool = False
    stratum: int | None = None
    remarks: str | None = None

    @property
    def misstatement(self) -> Decimal:
        return self.book - self.audited


def _rule(key: str, on: date | None, used: dict[str, Any]) -> Any:
    try:
        r = get_rule(key, on)
    except RuleNotFound:
        raise EvaluationError(f"The Rules Library has no value for '{key}'.") from None
    used[key] = {"version": r.version, "value": r.value, "status": r.status, "ref": r.ref}
    return r.value


def _ranks(values: Sequence[Decimal]) -> list[int]:
    """Rank = 1 + count of strictly larger values (ties share a rank, like COUNTIFS)."""
    return [1 + sum(1 for w in values if w > v) for v in values]


def _allowance(rows: list[dict[str, Any]], factors: Sequence[Decimal], warnings: list[str],
               sign: str) -> Decimal:
    ranked = [r for r in rows if not r["actual"]]
    if not ranked:
        return ZERO
    if not factors:
        raise EvaluationError(
            "The Rules Library has no incremental factors for this confidence level, so "
            "misstatements below the interval cannot be evaluated (DECISIONS D6).")
    total = ZERO
    for r, rank in zip(ranked, _ranks([abs(r["projected_exact"]) for r in ranked]), strict=True):
        if rank > len(factors):
            warnings.append(f"{sign} rank {rank} for {r['line_ref']} is beyond the "
                            f"{len(factors)} incremental factors in the Rules Library; the last "
                            "factor was used (DECISIONS D14).")
        f = factors[min(rank, len(factors)) - 1]
        ia = abs(r["projected_exact"]) * (f - ONE)
        r.update(rank=rank, incremental_factor=f, incremental_allowance_exact=ia,
                 incremental_allowance=q2(ia))
        total += ia
    return total


def evaluate_mus(items: Sequence[EvalItem], *, interval: Decimal, cf: Decimal,
                 tm: Decimal, confidence: str, on_date: date | None = None) -> dict[str, Any]:
    if interval <= 0 or tm <= 0:
        raise EvaluationError("Interval and tolerable misstatement must be greater than zero.")
    used: dict[str, Any] = {}
    warnings: list[str] = []
    rows: list[dict[str, Any]] = []
    for it in items:
        m = it.misstatement
        if m == 0:
            continue
        if it.book == 0:
            raise EvaluationError(f"{it.line_ref}: book value is zero, so the tainting cannot "
                                  "be computed.")
        top = it.book >= interval
        actual = top or it.key_item
        tainting = None if actual else m / it.book
        projected = m if actual else (tainting or ZERO) * interval
        rows.append({"line_ref": it.line_ref, "book_value": it.book, "audited_value": it.audited,
                     "misstatement": m, "top_stratum": top, "key_item": it.key_item,
                     "actual": actual, "tainting": tainting, "projected_exact": projected,
                     "projected": q2(projected), "direction":
                     "overstatement" if m > 0 else "understatement", "rank": None,
                     "incremental_factor": None, "incremental_allowance": None,
                     "remarks": it.remarks})
    over = [r for r in rows if r["direction"] == "overstatement"]
    under = [r for r in rows if r["direction"] == "understatement"]
    factors: list[Decimal] = []
    if any(not r["actual"] for r in rows):
        try:
            factors = [Decimal(str(x)) for x in _rule(f"sampling.mus.if.{confidence}",
                                                      on_date, used)]
        except EvaluationError:
            factors = []
    ia = _allowance(over, factors, warnings, "Overstatement")
    ia_u = _allowance(under, factors, warnings, "Understatement")
    bp = cf * interval
    sum_proj = sum((r["projected_exact"] for r in over), ZERO)
    uml = bp + sum_proj + ia
    sum_u = sum((-r["projected_exact"] for r in under), ZERO)
    uml_u = bp + sum_u + ia_u
    conclusion = ACCEPTABLE if uml <= tm else EXCEEDS
    if under:
        warnings.append("Understatements were found. They are projected separately and do not "
                        "reduce the overstatement UML (DECISIONS D15).")
    for r in rows:
        r["projected_exact"] = str(r["projected_exact"])
        r.pop("incremental_allowance_exact", None)
    return {
        "method": "mus", "confidence": confidence, "interval": interval, "cf": cf,
        "tolerable_misstatement": tm, "items_with_misstatement": len(rows), "items": rows,
        "basic_precision": q2(bp), "basic_precision_exact": bp,
        "sum_projected": q2(sum_proj), "sum_projected_exact": sum_proj,
        "incremental_allowance": q2(ia), "incremental_allowance_exact": ia,
        "uml": q2(uml), "uml_exact": uml, "conclusion": conclusion,
        "understatement": {"sum_projected": q2(sum_u), "incremental_allowance": q2(ia_u),
                           "upper_limit": q2(uml_u), "count": len(under)},
        "formula_text": (f"UML = BP {money(bp)} + projected {money(sum_proj)} + IA "
                         f"{money(ia)} = {money(uml)} vs TM {money(tm)}: {conclusion}"),
        "warnings": warnings, "rule_versions_used": used,
    }


def evaluate_ratio(items: Sequence[EvalItem], *, groups: Mapping[int | None, Decimal],
                   tm: Decimal) -> dict[str, Any]:
    """groups: population value represented by the sampled (non-actual) items, per stratum."""
    if tm <= 0:
        raise EvaluationError("Tolerable misstatement must be greater than zero.")
    actual_items = [i for i in items if i.key_item or i.top_stratum]
    by: dict[int | None, list[EvalItem]] = defaultdict(list)
    for i in items:
        if not (i.key_item or i.top_stratum):
            by[i.stratum].append(i)
    strata = []
    total = ZERO
    for key in sorted(groups, key=lambda k: -1 if k is None else k):
        its = by.get(key, [])
        book = sum((i.book for i in its), ZERO)
        mis = sum((i.misstatement for i in its), ZERO)
        ratio = mis / book if book else ZERO
        proj = ratio * groups[key]
        total += proj
        strata.append({"stratum": key, "sample_items": len(its), "sample_book": q2(book),
                       "sample_misstatement": q2(mis), "ratio": ratio,
                       "population_value": q2(groups[key]), "projected": q2(proj)})
    actual = sum((i.misstatement for i in actual_items), ZERO)
    projected = total + actual
    conclusion = ACCEPTABLE if projected <= tm else EXCEEDS
    return {
        "method": "ratio", "tolerable_misstatement": tm, "strata": strata,
        "actual_misstatement_key_items": q2(actual), "projected_misstatement": q2(projected),
        "projected_misstatement_exact": projected, "conclusion": conclusion,
        "items": [{"line_ref": i.line_ref, "book_value": i.book, "audited_value": i.audited,
                   "misstatement": i.misstatement, "stratum": i.stratum,
                   "key_item": i.key_item, "top_stratum": i.top_stratum, "remarks": i.remarks}
                  for i in items if i.misstatement != 0],
        "formula_text": (f"projected = sum(misstatement / book x population value) "
                         f"{money(total)} + actual {money(actual)} = {money(projected)} vs TM "
                         f"{money(tm)}: {conclusion}"),
        "warnings": ["Ratio projection is non-statistical: no allowance for sampling risk is "
                     "computed. If the projected misstatement is close to TM, consider further "
                     "work (ISA 530 A23, DECISIONS D16)."],
        "rule_versions_used": {},
    }


# ------------------------------------------------------------------ persistence / API
def evaluate_sample(sample_id: str, audited: Sequence[Mapping[str, Any]], *,
                    method: EvalMethod | None = None, tm_override: Decimal | None = None,
                    user_id: str | None = None) -> dict[str, Any]:
    from app.core.db import session_factory
    from app.models import Engagement, Sample, SampleItem
    from app.services.sampling import jsonable

    with session_factory()() as s:
        smp = s.get(Sample, sample_id)
        if smp is None or smp.result is None:  # pragma: no cover - API checks first
            raise EvaluationError("Sample not found.")
        res = dict(smp.result)
        eng = s.get(Engagement, smp.engagement_id)
        on = eng.fye if eng is not None else None
        db_items = {i.line_ref: i for i in s.query(SampleItem).filter_by(sample_id=smp.id)}
        given: dict[str, Mapping[str, Any]] = {}
        for a in audited:
            ref = str(a["line_ref"])
            if ref not in db_items:
                raise EvaluationError(f"{ref} is not an item of this sample.")
            if ref in given:
                raise EvaluationError(f"{ref} is listed twice.")
            given[ref] = a
        items: list[EvalItem] = []
        for ref, si in db_items.items():
            a = given.get(ref, {})
            aud = Decimal(str(a["audited_value"])) if "audited_value" in a else si.book_value
            attrs = si.attributes or {}
            items.append(EvalItem(ref, Decimal(si.book_value), Decimal(aud),
                                  top_stratum=si.top_stratum,
                                  key_item=bool(attrs.get("key_item")),
                                  stratum=attrs.get("stratum"), remarks=a.get("remarks")))
            si.audited_value = aud
            si.misstatement = Decimal(si.book_value) - Decimal(aud)
            if a.get("remarks") is not None:
                si.remarks = a["remarks"]
            if a.get("evidence_ref") is not None:
                si.evidence_ref = a["evidence_ref"]
        params = res.get("parameters") or {}
        tm_raw = tm_override if tm_override is not None else params.get("tolerable_misstatement")
        if tm_raw is None:
            raise EvaluationError("Tolerable misstatement is required to evaluate this sample.")
        tm = Decimal(str(tm_raw))
        is_mus = res.get("method") in ("mus", "key_items_mus")
        chosen: EvalMethod = method or ("mus" if is_mus else "ratio")
        if res.get("status") == "no_sampling" and not items:
            raise EvaluationError("This sample has no items to evaluate.")
        if chosen == "mus":
            if not is_mus or res.get("interval") is None:
                raise EvaluationError("MUS evaluation needs a MUS sample; use method 'ratio'.")
            out = evaluate_mus(items, interval=Decimal(str(res["interval"])),
                               cf=Decimal(str(res["cf_value"])), tm=tm,
                               confidence=str(params.get("confidence", "95")), on_date=on)
        else:
            out = evaluate_ratio(items, groups=_groups(res, items), tm=tm)
        out.update(sample_id=smp.id, sample_method=res.get("method"),
                   engine_version=f"{ENGINE_NAME} {ENGINE_VERSION}",
                   items_evaluated=len(given), items_in_sample=len(items),
                   evaluated_by=user_id)
        out = jsonable(out)
        res["evaluation"] = out
        smp.result = res
        s.commit()
    return dict(out)


def _groups(res: Mapping[str, Any], items: Sequence[EvalItem]) -> dict[int | None, Decimal]:
    pop = Decimal(str(res["population"]["value"]))
    if res.get("strata"):
        return {int(st["stratum"]): Decimal(str(st["value"])) for st in res["strata"]}
    actual = sum((i.book for i in items if i.key_item or i.top_stratum), ZERO)
    key_val = Decimal(str((res.get("key_items") or {}).get("value") or 0))
    top_val = Decimal(str((res.get("top_stratum") or {}).get("value") or 0))
    # key/top items represent only themselves; the rest of the population is projected
    return {None: pop - max(actual, key_val + top_val)}
