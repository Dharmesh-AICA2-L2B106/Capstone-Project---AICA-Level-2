"""Prompt 3.5 against golden_results.xlsx sheets "Projection" and "VAT".

Hand-worked example (95%, from the Projection sheet), with J = 233,906.91 / 3 per MUS_95:
- L00159: book 227,018.17 >= J 77,968.97, so top stratum. Actual 12,500.00.
- L00081: m 11,068.79 / 44,275.14 = 25.0000113% x J = 19,492.25. Rank 1, x (1.75 - 1)
  = 14,619.19.
- L00019: m 3,179.26 / 31,792.63 = 9.9999906% x J = 7,796.89. Rank 2, x (1.55 - 1)
  = 4,288.29.
- Totals: BP 3.00 x J = 233,906.91; Σ projected 39,789.14; IA 18,907.48.
- UML 292,603.53 > TM 280,000, so the conclusion is "Exceeds - further work".
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app.services.evaluation import EvalItem, evaluate_mus
from app.services.importer import parse_to_parquet, read_parquet_rows
from app.services.sampling import SampleRequest, run_sampling
from app.services.vat import run_vat_check
from tests.helpers import DATA, answer_key, golden_value

FYE = date(2025, 12, 31)
EPS = Decimal("0.000001")


@pytest.fixture(scope="module")
def gl_rows(tmp_path_factory: pytest.TempPathFactory) -> list[dict[str, Any]]:
    dest = tmp_path_factory.mktemp("gl") / "gl.parquet"
    parse_to_parquet(DATA / "dummy_gl.csv", dest)
    return list(read_parquet_rows(dest))


def _g(sheet: str, ref: str) -> Decimal:
    return Decimal(str(golden_value(sheet, ref)))


def _near(a: Any, b: Decimal) -> bool:
    return abs(Decimal(str(a)) - b) <= EPS


@pytest.mark.parametrize(("level", "first"), [("95", 10), ("90", 26)])
def test_projection_sheet_exact(gl_rows: list[dict[str, Any]], level: str, first: int) -> None:
    smp = run_sampling(gl_rows, SampleRequest(account_types=["Expense"], confidence=level,
                                              tolerable_misstatement=Decimal("280000"),
                                              seed=2025), period_end=FYE, dataset_hash="h")
    book = {i["line_id"]: i["value"] for i in smp["items"]}
    pop = {r["line_id"]: r["debit"] for r in gl_rows}
    items = []
    for row in range(first, first + 3):
        ref = str(golden_value("Projection", f"B{row}"))
        b = Decimal(pop[ref]).quantize(Decimal("0.01"))
        assert b == _g("Projection", f"C{row}")
        if ref in book:  # the engine sample (seed 2025) holds the line at the same value
            assert book[ref] == b
        items.append(EvalItem(ref, b, _g("Projection", f"D{row}")))
    res = evaluate_mus(items, interval=smp["interval"], cf=smp["cf_value"],
                       tm=Decimal("280000"), confidence=level, on_date=FYE)
    by = {r["line_ref"]: r for r in res["items"]}
    for row in range(first, first + 3):
        r = by[str(golden_value("Projection", f"B{row}"))]
        assert r["misstatement"] == _g("Projection", f"E{row}")
        assert r["top_stratum"] == (golden_value("Projection", f"F{row}") == "Yes")
        assert _near(r["projected_exact"], _g("Projection", f"H{row}"))
        if r["top_stratum"]:
            assert r["tainting"] is None and r["rank"] is None
        else:
            assert _near(r["tainting"], _g("Projection", f"G{row}"))
            assert r["rank"] == golden_value("Projection", f"I{row}")
            assert r["incremental_factor"] == _g("Projection", f"J{row}")
            assert abs(r["incremental_allowance"] - _g("Projection", f"K{row}")) <= Decimal(
                "0.005")
    base = first + 4  # B14 / B30 block
    assert _near(res["basic_precision_exact"], _g("Projection", f"B{base}"))
    assert _near(res["sum_projected_exact"], _g("Projection", f"B{base + 1}"))
    assert _near(res["incremental_allowance_exact"], _g("Projection", f"B{base + 2}"))
    assert _near(res["uml_exact"], _g("Projection", f"B{base + 3}"))
    assert res["conclusion"] == golden_value("Projection", f"B{base + 5}")
    expected = {"95": ("39789.14", "18907.48", "292603.53"),
                "90": ("48512.72", "19446.87", "305643.52")}[level]
    assert (str(res["sum_projected"]), str(res["incremental_allowance"]),
            str(res["uml"])) == expected
    assert res["rule_versions_used"][f"sampling.mus.if.{level}"]["ref"].endswith("@v1")


def test_vat_sheet_exact(gl_rows: list[dict[str, Any]]) -> None:
    res = run_vat_check(gl_rows)
    exc = {e["line_ref"]: e for e in res["exceptions"]}
    planted = {a["line_id"] for a in answer_key()
               if a["file"] == "dummy_gl.csv" and a["error_type"] == "output_vat_error"}
    assert set(exc) == planted and len(planted) == int(_g("VAT", "B19"))
    for row in range(6, 18):
        e = exc[str(golden_value("VAT", f"A{row}"))]
        assert e["net_amount"] == _g("VAT", f"C{row}").quantize(Decimal("0.01"))
        assert e["recorded_vat"] == _g("VAT", f"E{row}").quantize(Decimal("0.01"))
        assert e["expected_vat"] == _g("VAT", f"F{row}").quantize(Decimal("0.01"))
        assert e["difference"] == _g("VAT", f"G{row}").quantize(Decimal("0.01"))
        assert e["side"] == "output" and e["vat_code"] == golden_value("VAT", f"D{row}")
    assert res["exceptions_by_side"] == {"output": int(_g("VAT", "B20")),
                                         "input": int(_g("VAT", "B21"))}
    invalid = {t["line_ref"] for t in res["trn"]["invalid"]}
    assert len(invalid) == int(_g("VAT", "B33"))
    assert invalid == {str(golden_value("VAT", f"A{r}")) for r in range(25, 30)}
    assert invalid == {a["line_id"] for a in answer_key()
                       if a["file"] == "dummy_gl.csv" and a["error_type"] == "invalid_trn"}
    assert "L00002" not in invalid
    assert res["rule_versions_used"]["vat.rate.SR@v1"]["value"] == "0.05"
    assert res["rules_pending_verification"] is True


def test_vat_edge_file_trns(tmp_path: Path) -> None:
    parse_to_parquet(DATA / "edge_cases.csv", tmp_path / "e.parquet")
    res = run_vat_check(read_parquet_rows(tmp_path / "e.parquet"))
    planted = {a["line_id"] for a in answer_key()
               if a["file"] == "edge_cases.csv" and a["error_type"] == "invalid_trn"}
    assert {t["line_ref"] for t in res["trn"]["invalid"]} == planted
