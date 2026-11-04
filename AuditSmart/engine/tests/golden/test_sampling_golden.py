"""Prompt 3.3 against golden_results.xlsx MUS_95 / MUS_90 (firm_methodology_v0.2 §5)."""

from __future__ import annotations

from bisect import bisect_left
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app.services.importer import parse_to_parquet, read_parquet_rows
from app.services.sampling import SampleRequest, run_sampling
from tests.helpers import DATA, golden

FYE = date(2025, 12, 31)
CENT = Decimal("0.01")


@pytest.fixture(scope="module")
def gl_rows(tmp_path_factory: pytest.TempPathFactory) -> list[dict[str, Any]]:
    dest = tmp_path_factory.mktemp("gl") / "gl.parquet"
    parse_to_parquet(DATA / "dummy_gl.csv", dest)
    return list(read_parquet_rows(dest))


def _mus(rows: list[dict[str, Any]], level: str, seed: int = 2025, **kw: Any) -> dict[str, Any]:
    req = SampleRequest(account_types=["Expense"], confidence=level,
                        tolerable_misstatement=Decimal("280000"), seed=seed, **kw)
    return run_sampling(rows, req, period_end=FYE, dataset_hash="h")


def _g(sheet: str, ref: str) -> Decimal:
    return Decimal(str(golden()[sheet][ref].value))


def _close(a: Decimal, b: Decimal) -> bool:
    return abs(a - b) <= CENT


@pytest.mark.parametrize(("level", "sheet"), [("95", "MUS_95"), ("90", "MUS_90")])
def test_golden_mus_values(gl_rows: list[dict[str, Any]], level: str, sheet: str) -> None:
    r = _mus(gl_rows, level)
    assert _close(r["population"]["value"], _g(sheet, "B3"))
    assert r["cf_value"] == _g(sheet, "B6")
    assert r["ef_value"] == _g(sheet, "B9")
    assert r["n_required"] == int(_g(sheet, "B11"))
    assert _close(r["interval"], _g(sheet, "B12"))
    assert _close(r["basic_precision"], _g(sheet, "B13"))
    assert r["top_stratum"]["count"] == int(_g(sheet, "B14"))
    assert _close(r["top_stratum"]["value"], _g(sheet, "B15"))
    assert r["guide_formula_n"] == int(_g(sheet, "B20"))
    assert r["seed"] == int(_g(sheet, "B18"))
    assert r["credit_lines_excluded"]["count"] == 20
    assert r["cf_rule_version"] == f"sampling.mus.cf.{level}@v1"
    assert r["status"] == "selected"


def test_formula_text_95(gl_rows: list[dict[str, Any]]) -> None:
    r = _mus(gl_rows, "95")
    assert r["formula_text"] == ("n = ROUNDUP(12,553,004.07 x 3.00 / (280,000.00 - 28,000.00 x "
                                 "1.6), 0) = 161; J = 77,968.97")


def _population_sheet() -> tuple[list[str], list[Decimal], list[Decimal]]:
    ws = golden()["Population"]
    ids, pop, cum = [], [], []
    for row in ws.iter_rows(min_row=2, max_row=3001, values_only=True):
        ids.append(str(row[0]))
        pop.append(Decimal(str(row[21])))
        cum.append(Decimal(str(row[22])))
    return ids, pop, cum


@pytest.mark.parametrize("level", ["95", "90"])
@pytest.mark.parametrize("seed", [2025, 1, 777])
def test_selection_matches_golden_countif_rule(gl_rows: list[dict[str, Any]], level: str,
                                               seed: int) -> None:
    """Independent re-implementation of the sheet: row = COUNTIF(cum, "<" & point) + 1."""
    r = _mus(gl_rows, level, seed=seed)
    ids, _pop, cum = _population_sheet()
    start, j = Decimal(r["random_start"]), r["interval"]
    expected: dict[str, int] = {}
    for k in range(r["n_required"]):
        point = start + k * j
        row = sum(1 for c in cum if c < point) + 1
        expected[ids[row - 1]] = expected.get(ids[row - 1], 0) + 1
    got = {i["line_id"]: i["hits"] for i in r["items"]}
    assert got == expected


def test_top_stratum_selected_100_percent(gl_rows: list[dict[str, Any]]) -> None:
    ids, pop, _cum = _population_sheet()
    for level in ("95", "90"):
        for seed in (2025, 3, 99_999):
            r = _mus(gl_rows, level, seed=seed)
            top = {ids[i] for i, v in enumerate(pop) if v >= r["interval"]}
            picked = {i["line_id"] for i in r["items"]}
            assert top <= picked
            assert top == {i["line_id"] for i in r["top_stratum"]["items"]}


def test_same_seed_same_sample_and_subset(gl_rows: list[dict[str, Any]]) -> None:
    a, b = _mus(gl_rows, "95", seed=42), _mus(gl_rows, "95", seed=42)
    assert a["items"] == b["items"] and a["random_start"] == b["random_start"]
    c = _mus(gl_rows, "95", seed=43)
    assert c["random_start"] != a["random_start"]
    pop_ids = {r["line_id"] for r in gl_rows
               if r["account_type"] == "Expense" and r["debit"] > 0}
    assert {i["line_id"] for i in a["items"]} <= pop_ids
    excluded = {i["line_id"] for i in a["credit_lines_excluded"]["items"]}
    assert not excluded & pop_ids


def test_random_start_within_interval(gl_rows: list[dict[str, Any]]) -> None:
    for seed in range(20):
        r = _mus(gl_rows, "90", seed=seed)
        assert Decimal(0) <= r["random_start"] < r["interval"]
        assert r["random_start"] == r["random_start"].quantize(CENT)


def test_guide_formula_option(gl_rows: list[dict[str, Any]]) -> None:
    r = _mus(gl_rows, "95", size_formula="guide")
    assert r["n_required"] == 135
    assert r["formula_text"].startswith("n = ceil(12,553,004.07 x 3.00 / 280,000.00) = 135")


def test_seed_2025_start_documented() -> None:
    """docs/step3.3_golden_start.md records the engine start values to paste into B17."""
    doc = Path(__file__).resolve().parents[3] / "docs" / "step3.3_golden_start.md"
    text = doc.read_text(encoding="utf-8")
    assert "MUS_95" in text and "MUS_90" in text and "seed 2025" in text


def test_bisect_rule_equals_countif_on_ties() -> None:
    cum = [Decimal(x) for x in ("10", "10", "25", "40")]
    for point in (Decimal("10"), Decimal("10.01"), Decimal("25"), Decimal("0.5")):
        assert bisect_left(cum, point) + 1 == sum(1 for c in cum if c < point) + 1


def test_rules_library_factors_match_golden_tables() -> None:
    from app.services.rules import get_rule

    ws = golden()["Projection"]
    for col, level in ((15, "95"), (16, "90")):
        sheet = [Decimal(str(ws.cell(r, col).value)) for r in range(5, 10)]
        assert [Decimal(x) for x in get_rule(f"sampling.mus.if.{level}", FYE).value] == sheet
