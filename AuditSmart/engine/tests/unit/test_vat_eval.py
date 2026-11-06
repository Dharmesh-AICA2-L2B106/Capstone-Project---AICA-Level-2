"""Prompt 3.5 unit tests: VAT recalculation and MUS / ratio evaluation."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from app.services.evaluation import EvalItem, EvaluationError, _ranks, evaluate_mus, evaluate_ratio
from app.services.vat import VatError, likely_cause, round2, run_vat_check, side_of, trn_reason

D = Decimal
ON = date(2025, 6, 30)


def _row(**kw: Any) -> dict[str, Any]:
    base = {"line_id": "L1", "row_no": 2, "account_type": "Revenue", "vat_code": "SR",
            "net_amount": D("100"), "vat_amount": D("5"), "entry_date": ON, "trn": ""}
    return {**base, **kw}


def test_round_half_up_and_cause() -> None:
    assert round2(D("0.125")) == D("0.13") and round2(D("-0.125")) == D("-0.13")
    assert likely_cause(D("100"), D("0"), D("0.05")) == "VAT not charged"
    assert likely_cause(D("100"), D("5.25"), D("0.05")).startswith("VAT computed on the gross")
    assert likely_cause(D("100"), D("10"), D("0.05")) == "Different rate applied (effective 10%)"
    assert likely_cause(D("100"), D("6"), D("0")) == "Different rate applied (effective 6%)"
    assert side_of({"account_type": " revenue "}) == "output" and side_of({}) == "input"


def test_trn_reasons() -> None:
    p = re.compile(r"^100\d{12}$")
    assert trn_reason("100123456789012", p) is None
    assert trn_reason("10012345678901X", p) == "contains non-digits"
    assert trn_reason("200123456789012", p) == "does not start with 100"
    assert trn_reason("1001", p) == "4 characters, 15 expected"
    assert trn_reason("100123456789012", re.compile("^9")) == "does not match the TRN pattern"


def test_vat_lines() -> None:
    rows = [_row(), _row(line_id="L2", vat_amount=D("5.01")),
            _row(line_id="L3", vat_amount=D("5.02"), account_type="Expense"),
            _row(line_id="L4", vat_code="ZR", vat_amount=D("0")),
            _row(line_id="L5", vat_code="XX"), _row(line_id="L6", net_amount=None),
            _row(line_id="L7", vat_code=""), _row(line_id="L8", entry_date=None,
                                                   posting_date=ON, trn="12")]
    res = run_vat_check(rows, dataset_hash="h")
    exc = {e["line_ref"]: e for e in res["exceptions"]}
    assert set(exc) == {"L3", "L5", "L6"}  # 0.01 is within tolerance
    assert exc["L3"]["side"] == "input" and exc["L3"]["difference"] == D("0.02")
    assert exc["L5"]["exception"] == "unknown_code" and exc["L6"]["exception"] == "missing_net"
    assert res["lines_checked"] == 7 and res["trn"]["checked"] == 1
    assert res["trn"]["invalid"][0]["line_ref"] == "L8"
    out = run_vat_check(rows, sides=["output"])
    assert out["exceptions_by_side"] == {"output": 2} and out["lines_checked"] == 6
    sr = next(s for s in res["summary"] if s["side"] == "output" and s["vat_code"] == "SR")
    assert sr["lines"] == 4 and sr["exceptions"] == 1


@pytest.mark.parametrize("sides", [[], ["both"]])
def test_vat_bad_sides(sides: list[str]) -> None:
    with pytest.raises(VatError):
        run_vat_check([], sides=sides)


def test_vat_missing_rules_for_date() -> None:
    with pytest.raises(VatError, match="tolerance"):
        run_vat_check([_row(entry_date=date(2017, 1, 1))])
    with pytest.raises(VatError, match="TRN pattern"):
        run_vat_check([_row(entry_date=date(2000, 1, 1), trn="100123456789012")])


def test_ranks_ties() -> None:
    assert _ranks([D(5), D(9), D(5), D(1)]) == [2, 1, 2, 4]


def _mus(items: list[EvalItem], tm: str = "1000", conf: str = "95") -> dict[str, Any]:
    return evaluate_mus(items, interval=D("100"), cf=D("3"), tm=D(tm), confidence=conf,
                        on_date=ON)


def test_mus_no_errors_and_key_items() -> None:
    r = _mus([EvalItem("a", D("50"), D("50"))])
    assert r["uml"] == D("300.00") and r["conclusion"] == "Acceptable" and not r["items"]
    k = _mus([EvalItem("k", D("50"), D("40"), key_item=True)])
    assert k["items"][0]["actual"] and k["sum_projected"] == D("10.00")
    assert k["incremental_allowance"] == D("0.00") and k["rule_versions_used"] == {}


def test_mus_rank_beyond_table_and_understatement() -> None:
    items = [EvalItem(f"i{n}", D("10"), D("10") - D(n + 1) / 10) for n in range(12)]
    items.append(EvalItem("u", D("10"), D("12")))
    r = _mus(items, tm="350")
    assert any("D14" in w for w in r["warnings"]) and any("D15" in w for w in r["warnings"])
    assert r["conclusion"] == "Exceeds - further work"
    assert r["understatement"]["count"] == 1 and r["understatement"]["sum_projected"] == D(
        "20.00")
    assert r["sum_projected"] == D("78.00")  # understatement does not reduce it


def test_mus_errors() -> None:
    with pytest.raises(EvaluationError, match="greater than zero"):
        evaluate_mus([], interval=D(0), cf=D(3), tm=D(1), confidence="95")
    with pytest.raises(EvaluationError, match="book value is zero"):
        _mus([EvalItem("z", D("0"), D("-5"))])
    with pytest.raises(EvaluationError, match="D6"):
        _mus([EvalItem("a", D("50"), D("40"))], conf="80")


def test_ratio() -> None:
    items = [EvalItem("a", D("100"), D("90"), stratum=1), EvalItem("b", D("100"), D("100"),
                                                                   stratum=1),
             EvalItem("t", D("900"), D("850"), top_stratum=True)]
    r = evaluate_ratio(items, groups={1: D("1000"), 2: D("500")}, tm=D("100"))
    assert [s["projected"] for s in r["strata"]] == [D("50.00"), D("0.00")]
    assert r["actual_misstatement_key_items"] == D("50.00")
    assert r["projected_misstatement"] == D("100.00") and r["conclusion"] == "Acceptable"
    assert "D16" in r["warnings"][0] and len(r["items"]) == 2
    with pytest.raises(EvaluationError):
        evaluate_ratio(items, groups={}, tm=D("0"))
