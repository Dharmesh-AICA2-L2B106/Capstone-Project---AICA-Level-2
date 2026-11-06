"""Benford's law, first-digit test (SPEC 3.2, prompt 3.4).

Amounts below the rule ``benford.min_amount`` (10) are excluded. Conformity uses the
mean absolute deviation (MAD) against Nigrini's first-digit thresholds from the rules
(0.006 close, 0.012 acceptable, 0.015 marginal, above that nonconformity). The chi-square
statistic (8 degrees of freedom) uses scipy for the critical value and p-value. All
arithmetic is deterministic, with no AI involved.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from app.services.rules import RuleNotFound, get_rule

IMPLEMENTED_BY_PROMPT = "3.4"

DIGITS = tuple(range(1, 10))
EXPECTED = {d: math.log10(1 + 1 / d) for d in DIGITS}


class BenfordError(ValueError):
    pass


@dataclass
class _Rules:
    on_date: date | None
    used: dict[str, dict[str, Any]] = field(default_factory=dict)

    def value(self, key: str) -> Any:
        try:
            r = get_rule(key, self.on_date)
        except RuleNotFound:
            raise BenfordError(f"The Rules Library has no value for '{key}'.") from None
        self.used[key] = {"version": r.version, "value": r.value, "status": r.status, "ref": r.ref}
        return r.value


def first_digit(amount: Decimal) -> int:
    """Leading non-zero digit of |amount| (amount must be non-zero)."""
    a = abs(amount)
    if a == 0:
        raise BenfordError("Zero has no first digit.")
    digits = format(a.normalize(), "f").replace(".", "").lstrip("0")
    return int(digits[0])


def conclusion_for(mad: float, thresholds: tuple[float, float, float]) -> str:
    close, acceptable, marginal = thresholds
    if mad <= close:
        return "Close conformity"
    if mad <= acceptable:
        return "Acceptable conformity"
    if mad <= marginal:
        return "Marginally acceptable conformity"
    return "Nonconformity"


def run_benford(
    amounts: Iterable[Decimal], *, on_date: date | None = None, min_amount: Decimal | None = None
) -> dict[str, Any]:
    from scipy.stats import chi2

    rules = _Rules(on_date)
    floor = Decimal(
        str(min_amount if min_amount is not None else rules.value("benford.min_amount"))
    )
    thresholds_raw = rules.value("benford.mad.first_digit")
    thresholds = (float(thresholds_raw[0]), float(thresholds_raw[1]), float(thresholds_raw[2]))
    alpha = float(rules.value("benford.chi2.alpha"))
    counts = dict.fromkeys(DIGITS, 0)
    excluded = 0
    for a in amounts:
        if a is None or abs(a) < floor:
            excluded += 1
            continue
        counts[first_digit(a)] += 1
    n = sum(counts.values())
    if n == 0:
        raise BenfordError(f"No amounts of at least {floor} to test.")
    chart, chi_sq, abs_dev = [], 0.0, 0.0
    for d in DIGITS:
        exp_n = EXPECTED[d] * n
        act_p = counts[d] / n
        chi_sq += (counts[d] - exp_n) ** 2 / exp_n
        abs_dev += abs(act_p - EXPECTED[d])
        # Nigrini z-statistic with continuity correction
        se = math.sqrt(EXPECTED[d] * (1 - EXPECTED[d]) / n)
        z = max(0.0, abs(act_p - EXPECTED[d]) - 1 / (2 * n)) / se
        chart.append(
            {
                "digit": d,
                "count": counts[d],
                "expected_count": round(exp_n, 2),
                "actual_pct": round(act_p * 100, 2),
                "expected_pct": round(EXPECTED[d] * 100, 2),
                "z": round(z, 3),
                "significant": z > 1.96,
            }
        )
    mad = abs_dev / 9
    critical = float(chi2.ppf(1 - alpha, 8))
    p_value = float(chi2.sf(chi_sq, 8))
    concl = conclusion_for(mad, thresholds)
    spikes = [c["digit"] for c in chart if c["significant"]]
    text = (
        f"First-digit test on {n:,} amounts >= {floor:,} ({excluded:,} excluded): MAD "
        f"{mad:.4f} - {concl}. Chi-square {chi_sq:.2f} vs critical {critical:.2f} "
        f"(alpha {alpha}, 8 df, p = {p_value:.4f})."
    )
    if spikes:
        text += (
            " Digits with significant deviation (z > 1.96): " + ", ".join(map(str, spikes)) + "."
        )
    if concl == "Nonconformity" or chi_sq > critical:
        text += " Consider targeted JE testing of the over-represented digits."
    return {
        "test": "first_digit",
        "n": n,
        "excluded_below_min": excluded,
        "min_amount": str(floor),
        "mad": round(mad, 6),
        "mad_thresholds": [str(t) for t in thresholds_raw],
        "conclusion": concl,
        "chi_square": round(chi_sq, 4),
        "chi_square_critical": round(critical, 4),
        "chi_square_alpha": alpha,
        "p_value": round(p_value, 6),
        "chi_square_reject": chi_sq > critical,
        "significant_digits": spikes,
        "chart": chart,
        "conclusion_text": text,
        "rule_versions_used": rules.used,
        "rules_pending_verification": any(v["status"] != "approved" for v in rules.used.values()),
    }


def benford_for_dataset(
    dataset_id: str, *, account_types: list[str] | None = None, min_amount: Decimal | None = None
) -> dict[str, Any]:
    """Benford on a validated dataset's line amounts (debit or credit)."""
    from pathlib import Path

    from app.core.db import session_factory
    from app.models import Engagement
    from app.services.datasets import assert_usable
    from app.services.importer import read_parquet_rows

    ds = assert_usable(dataset_id)
    with session_factory()() as s:
        eng = s.get(Engagement, ds.engagement_id)
        on_date = eng.fye if eng is not None else None
    types = {t.lower() for t in account_types or []}
    amounts = (
        (r.get("debit") or Decimal(0)) or (r.get("credit") or Decimal(0))
        for r in read_parquet_rows(Path(ds.parquet_ref or ""))
        if not types or str(r.get("account_type") or "").lower() in types
    )
    out = run_benford(amounts, on_date=on_date, min_amount=min_amount)
    out.update(
        {"dataset_id": ds.id, "dataset_hash": ds.sha256, "account_types": sorted(types) or None}
    )
    return out
