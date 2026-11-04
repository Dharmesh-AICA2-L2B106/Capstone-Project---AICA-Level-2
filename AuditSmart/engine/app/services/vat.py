"""Output VAT recalculation and TRN checks (SPEC 3.2 item 6, prompt 3.5).

For each line with a VAT code, the engine uses the rule version valid on the invoice date:
- the rate by code (``vat.rate.<CODE>``)
- the tolerance (``vat.tolerance``)
- the TRN pattern (``validation.trn_pattern``)

Expected VAT = net x rate, rounded HALF_UP to 2 dp. A line is an exception when
|recorded - expected| > tolerance. The arithmetic is deterministic Decimal, with no AI.
The "likely cause" text only describes a variance; it never decides whether a line is
an exception.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.services.rules import Rule, RuleNotFound, get_rule
from app.services.sampling import money
from app.version import ENGINE_NAME, ENGINE_VERSION

IMPLEMENTED_BY_PROMPT = "3.5"

ZERO = Decimal(0)
CENT = Decimal("0.01")
SIDES = ("output", "input")


class VatError(ValueError):
    pass


def round2(v: Decimal) -> Decimal:
    return v.quantize(CENT, ROUND_HALF_UP)


@dataclass
class _Rules:
    """Rule lookups cached per (key, date); records every version used."""

    used: dict[str, dict[str, Any]] = field(default_factory=dict)
    _cache: dict[tuple[str, date | None], Rule | None] = field(default_factory=dict)

    def get(self, key: str, on: date | None) -> Rule | None:
        ck = (key, on)
        if ck not in self._cache:
            try:
                self._cache[ck] = get_rule(key, on)
            except RuleNotFound:
                self._cache[ck] = None
        r = self._cache[ck]
        if r is not None:
            self.used[r.ref] = {"rule_key": r.rule_key, "version": r.version, "value": r.value,
                                "status": r.status, "effective_from": r.effective_from}
        return r

    @property
    def pending(self) -> bool:
        return any(u["status"] != "approved" for u in self.used.values())


def side_of(row: Mapping[str, Any]) -> str:
    return "output" if str(row.get("account_type") or "").strip().lower() == "revenue" \
        else "input"


def likely_cause(net: Decimal, recorded: Decimal, rate: Decimal) -> str:
    """Plain description of a variance (informational only)."""
    if recorded == 0:
        return "VAT not charged"
    if rate > 0 and abs(recorded - round2(net * (1 + rate) * rate)) <= CENT:
        return "VAT computed on the gross amount (net x (1 + rate) x rate)"
    if net != 0:
        eff = (recorded / net * 100).quantize(Decimal("0.01"), ROUND_HALF_UP)
        return f"Different rate applied (effective {eff.normalize():f}%)"
    return "Other difference"  # pragma: no cover - net 0 with recorded VAT is caught above


def trn_reason(trn: str, pattern: re.Pattern[str]) -> str | None:
    """Why a non-blank TRN fails the pattern; None when valid."""
    if pattern.match(trn):
        return None
    parts = []
    if not trn.isdigit():
        parts.append("contains non-digits")
    if len(trn) != 15:
        parts.append(f"{len(trn)} characters, 15 expected")
    if not trn.startswith("100"):
        parts.append("does not start with 100")
    return "; ".join(parts) or "does not match the TRN pattern"


def _dec(v: Any) -> Decimal | None:
    if v is None or v == "":
        return None
    return v if isinstance(v, Decimal) else Decimal(str(v))


def run_vat_check(rows: Iterable[Mapping[str, Any]], *, sides: Sequence[str] = SIDES,
                  dataset_hash: str | None = None) -> dict[str, Any]:
    bad_sides = set(sides) - set(SIDES)
    if bad_sides or not sides:
        raise VatError("sides must be one or both of: output, input.")
    rules = _Rules()
    lines: list[dict[str, Any]] = []
    exceptions: list[dict[str, Any]] = []
    trn_invalid: list[dict[str, Any]] = []
    summary: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {"lines": 0, "net": ZERO, "recorded": ZERO, "expected": ZERO,
                 "difference": ZERO, "exceptions": 0})
    trn_checked = 0
    for r in rows:
        on = r.get("entry_date") or r.get("posting_date")
        trn = str(r.get("trn") or "").strip()
        if trn:
            trn_checked += 1
            tr = rules.get("validation.trn_pattern", on)
            if tr is None:
                raise VatError("The Rules Library has no TRN pattern for "
                               f"{on}; add 'validation.trn_pattern'.")
            reason = trn_reason(trn, re.compile(str(tr.value)))
            if reason:
                trn_invalid.append({"line_ref": r.get("line_id") or str(r.get("row_no")),
                                    "row_no": r.get("row_no"), "trn": trn, "reason": reason,
                                    "party_id": r.get("party_id") or None,
                                    "rule_version": tr.ref})
        code = str(r.get("vat_code") or "").strip().upper()
        side = side_of(r)
        if not code or side not in sides:
            continue
        ref = r.get("line_id") or str(r.get("row_no"))
        net, recorded = _dec(r.get("net_amount")), round2(_dec(r.get("vat_amount")) or ZERO)
        net = round2(net) if net is not None else None
        base = {"line_ref": ref, "row_no": r.get("row_no"), "voucher_no": r.get("voucher_no"),
                "invoice_no": r.get("invoice_no") or None, "invoice_date": on, "side": side,
                "vat_code": code, "account_code": r.get("account_code"),
                "net_amount": net, "recorded_vat": recorded}
        rate_rule = rules.get(f"vat.rate.{code}", on)
        tol_rule = rules.get("vat.tolerance", on)
        if tol_rule is None:
            raise VatError(f"The Rules Library has no VAT tolerance for {on}; add "
                           "'vat.tolerance'.")
        s = summary[(side, code)]
        s["lines"] += 1
        s["recorded"] += recorded
        if rate_rule is None or net is None:
            item = {**base, "expected_vat": None, "difference": None, "rate": None,
                    "exception": "unknown_code" if rate_rule is None else "missing_net",
                    "likely_cause": (f"No VAT rate in the Rules Library for code '{code}' on "
                                     f"{on}" if rate_rule is None else
                                     "The line has a VAT code but no net amount"),
                    "rule_versions": [tol_rule.ref]}
            s["exceptions"] += 1
            exceptions.append(item)
            lines.append(item)
            continue
        rate, tol = Decimal(str(rate_rule.value)), Decimal(str(tol_rule.value))
        expected = round2(net * rate)
        diff = recorded - expected
        is_exc = abs(diff) > tol
        item = {**base, "rate": rate, "expected_vat": expected, "difference": diff,
                "tolerance": tol, "exception": "variance" if is_exc else None,
                "likely_cause": likely_cause(net, recorded, rate) if is_exc else None,
                "rule_versions": [rate_rule.ref, tol_rule.ref]}
        s["net"] += net
        s["expected"] += expected
        s["difference"] += diff
        if is_exc:
            s["exceptions"] += 1
            exceptions.append(item)
        lines.append(item)
    summ = [{"side": k[0], "vat_code": k[1], **{x: (money(v) if isinstance(v, Decimal) else v)
                                                 for x, v in val.items()}}
            for k, val in sorted(summary.items())]
    by_side = {sd: sum(1 for e in exceptions if e["side"] == sd) for sd in sides}
    return {
        "engine_version": f"{ENGINE_NAME} {ENGINE_VERSION}", "dataset_hash": dataset_hash,
        "sides": list(sides), "lines_checked": len(lines), "exceptions_count": len(exceptions),
        "exceptions_by_side": by_side, "summary": summ, "exceptions": exceptions,
        "net_difference": money(sum((e["difference"] or ZERO for e in exceptions), ZERO)),
        "trn": {"checked": trn_checked, "invalid_count": len(trn_invalid),
                "invalid": trn_invalid},
        "rule_versions_used": rules.used, "rules_pending_verification": rules.pending,
        "basis": "Expected VAT = ROUND_HALF_UP(net x rate, 2) with the rate, tolerance and "
                 "TRN pattern taken from the rule version valid on each invoice date.",
    }


def vat_check_for_dataset(dataset_id: str, *, sides: Sequence[str] = SIDES) -> dict[str, Any]:
    from pathlib import Path

    from app.services.datasets import assert_usable
    from app.services.importer import read_parquet_rows
    from app.services.sampling import jsonable

    ds = assert_usable(dataset_id)
    if ds.parquet_ref is None:  # pragma: no cover - assert_usable guarantees a parsed file
        raise VatError("The dataset has not been read yet.")
    res = run_vat_check(read_parquet_rows(Path(ds.parquet_ref)), sides=sides,
                        dataset_hash=ds.sha256)
    res["dataset_id"] = ds.id
    return dict(jsonable(res))
