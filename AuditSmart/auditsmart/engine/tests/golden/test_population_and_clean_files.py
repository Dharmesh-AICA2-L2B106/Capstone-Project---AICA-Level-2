"""Golden checks: parsed totals agree to golden_results.xlsx; clean files are clean."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from app.services.importer import parse_to_parquet, read_parquet_rows
from app.services.validation import validate_parquet
from tests.helpers import DATA, golden_value

pytestmark = pytest.mark.golden


def _run(name: str, tmp: Path, chunk_rows: int = 1000):  # type: ignore[no-untyped-def]
    out = tmp / f"{name}.parquet"
    res = parse_to_parquet(DATA / name, out, chunk_rows=chunk_rows)
    return res, validate_parquet(out, missing_cols=res.missing_columns), out


def test_dummy_gl_population_matches_golden(tmp_path: Path) -> None:
    res, rep, out = _run("dummy_gl.csv", tmp_path)
    assert res.chunks == 3
    assert res.total_dr == Decimal(str(golden_value("Population", "B3003")))
    assert res.total_cr == Decimal(str(golden_value("Population", "B3004")))
    assert res.rows == golden_value("Population", "B3006") == 3000
    # test population (expense debits) – used by prompt 3.3 sampling
    exp = [r for r in read_parquet_rows(out) if r["account_type"] == "Expense" and r["debit"] > 0]
    assert sum(r["debit"] for r in exp) == Decimal(str(golden_value("Population", "B3008")))
    assert len(exp) == golden_value("Population", "B3009")
    assert rep.critical == 0 and not rep.blocked


def test_dummy_gl_only_trn_warnings_match_answer_key(tmp_path: Path) -> None:
    from tests.helpers import answer_key

    _, rep, _ = _run("dummy_gl.csv", tmp_path)
    assert [i.code for i in rep.issues] == ["invalid_trn"]
    expected = {int(r["row_no"]) for r in answer_key()
                if r["file"] == "dummy_gl.csv" and r["error_type"] == "invalid_trn"}
    assert set(rep.issues[0].rows) == expected and len(expected) == 5


def test_fy2021_2022_clean(tmp_path: Path) -> None:
    res, rep, _ = _run("fy2021_2022.csv", tmp_path)
    assert rep.issues == [] and res.rows == 400 and res.total_dr == res.total_cr
