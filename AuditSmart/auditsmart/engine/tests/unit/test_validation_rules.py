from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.services import rules
from app.services.importer import parse_to_parquet, to_csv_bytes
from app.services.validation import fmt_rows, validate_parquet, validate_rows

HDR = ["line_id", "posting_date", "voucher_no", "account_code", "debit", "credit", "trn"]


def _gl(tmp: Path, rows: list[list[str]], name: str = "g.csv") -> Path:
    p = tmp / name
    p.write_bytes(to_csv_bytes([HDR, *rows]))
    out = tmp / f"{name}.parquet"
    parse_to_parquet(p, out)
    return out


def test_voucher_gaps_and_precision_and_bad_amount(tmp_path: Path) -> None:
    rows = []
    for i, n in enumerate([1, 2, 5, 9], 1):
        rows += [[f"A{i}", "2025-01-01", f"JV-{n:04d}", "6100", "10.005", ""],
                 [f"B{i}", "2025-01-01", f"JV-{n:04d}", "2010", "", "10.005"]]
    rows += [["C1", "2025-01-01", "PV-1", "6100", "12x", "0"],
             ["C2", "2025-01-01", "", "", "0", "0"]]
    rep = validate_parquet(_gl(tmp_path, rows))
    by = {i.code: i for i in rep.issues}
    assert by["voucher_gap"].row_count == 5
    assert "JV-0003, JV-0004, JV-0006, JV-0007, JV-0008" in by["voucher_gap"].message
    assert by["amount_precision"].severity == "warning"
    assert by["unreadable_amount"].rows == [9] and by["unreadable_amount"].severity == "critical"
    assert by["missing_mandatory_field"].rows == [10]
    assert by["blank_account"].rows == [10]


def test_tolerance_from_rules(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    out = _gl(tmp_path, [["1", "2025-01-01", "JV-1", "6100", "100.05", ""],
                         ["2", "2025-01-01", "JV-1", "2010", "", "100.00"]])
    assert {i.code for i in validate_parquet(out).issues} == {"unbalanced_voucher",
                                                               "total_out_of_balance"}
    real = rules.get_rule

    def fake(key: str, on_date: date | None = None) -> rules.Rule:
        r = real(key, on_date)
        if key == "validation.balance_tolerance":
            return rules.Rule(r.rule_key, 2, r.effective_from, "0.10", r.status, r.source_ref)
        return r

    monkeypatch.setattr("app.services.validation.get_rule", fake)
    assert validate_parquet(out).issues == []


def test_gl_vs_tb(tmp_path: Path) -> None:
    gl = _gl(tmp_path, [["1", "2025-01-01", "JV-1", "6100", "100", ""],
                        ["2", "2025-01-01", "JV-1", "2010", "", "100"]])
    tb_csv = tmp_path / "tb.csv"
    tb_csv.write_bytes(to_csv_bytes([["Account", "Closing Balance"], ["6100", "100"],
                                     ["2010", "-90"], ["", "0"]]))
    parse_to_parquet(tb_csv, tmp_path / "tb.parquet", kind="TB")
    tb_rep = validate_parquet(tmp_path / "tb.parquet", kind="TB")
    assert [i.code for i in tb_rep.issues] == ["blank_account"]
    rep = validate_parquet(gl, tb_path=tmp_path / "tb.parquet")
    gl_tb = next(i for i in rep.issues if i.code == "gl_tb_difference")
    assert gl_tb.severity == "warning" and "2010 (AED -10.00)" in gl_tb.message


def test_rows_capped_at_50() -> None:
    rows = [{"row_no": i, "line_id": f"L{i}", "voucher_no": "V1", "account_code": "",
             "debit": Decimal("0"), "credit": Decimal("0"), "posting_date_raw": "2025-01-01",
             "trn": "", "parse_issues": ""} for i in range(1, 121)]
    rep = validate_rows(rows)
    blank = next(i for i in rep.issues if i.code == "blank_account")
    assert len(blank.rows) == 50 and blank.row_count == 120
    assert "and 110 more" in blank.message
    assert fmt_rows([7], 1) == "row 7"


def test_rules_lookup() -> None:
    assert rules.get_rule("validation.balance_tolerance").value == "0.00"
    assert rules.get_rule("validation.trn_pattern").status == "pending_verification"
    assert rules.get_rule("validation.trn_pattern").ref == "validation.trn_pattern@v1"
    with pytest.raises(rules.RuleNotFound):
        rules.get_rule("nope")
    with pytest.raises(rules.RuleNotFound):
        rules.get_rule("validation.balance_tolerance", date(2000, 1, 1))
