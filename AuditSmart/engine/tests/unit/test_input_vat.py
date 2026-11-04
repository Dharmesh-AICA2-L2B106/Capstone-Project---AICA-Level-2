"""Prompt 3.12 unit tests: input-VAT checks (Decisions 13 and 17 of 2026), pure engine."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from app.services.input_vat import (
    CHECKS,
    InputVatError,
    Params,
    Supplier,
    _date,
    _dec,
    add_months,
    parse_register_csv,
    run_input_vat,
)

D = Decimal
EFF = date(2026, 10, 1)


def _row(i: int, **kw: Any) -> dict[str, Any]:
    base = {"line_id": f"L{i:03d}", "row_no": i + 1, "voucher_no": f"PI-{i}",
            "posting_date": date(2026, 10, 15), "account_code": "5000",
            "account_name": "Purchases", "debit": D("1000"), "party_id": "S1",
            "party_name": "Supplier one", "vat_amount": D("50"), "vat_code": "SR"}
    return {**base, **kw}


def _by(res: dict[str, Any], check: str) -> list[dict[str, Any]]:
    return [e for e in res["exceptions"] if e["check"] == check]


def test_helpers() -> None:
    assert add_months(date(2026, 3, 31), -1) == date(2026, 2, 28)
    assert add_months(date(2024, 3, 31), -1) == date(2024, 2, 29)
    assert add_months(date(2026, 1, 15), -12) == date(2025, 1, 15)
    assert add_months(date(2026, 11, 30), 3) == date(2027, 2, 28)
    assert _dec(None) == 0 and _dec("x") == 0 and _dec("1.5") == D("1.5")
    assert _date("2026-01-02T00:00") == date(2026, 1, 2) and _date("bad") is None
    assert _date(None) is None


def test_params() -> None:
    assert Params.build(None).effective_date_override is None
    assert Params.build({"effective_date_override": "2025-10-01"}).effective_date_override \
        == date(2025, 10, 1)
    with pytest.raises(InputVatError, match="Unknown"):
        Params.build({"x": 1})
    with pytest.raises(InputVatError, match="YYYY-MM-DD"):
        Params.build({"effective_date_override": "01/10/2025"})


def test_register_parse_aliases_and_errors() -> None:
    csv = (b"\xef\xbb\xbfparty_id,party_name,verified_on,verification_ref,risk_indicators,"
           b"bank_evidence\nS1,One,2026-09-01,V1,shell; new|,B1\n,blank,,,,\nS1,dup,,,,\n"
           b"S2,Two,01/02/2026,,,\nS3,Three,,,,\n")
    sup, err = parse_register_csv(csv)
    assert [s.supplier_id for s in sup] == ["S1", "S3"]
    assert sup[0].risk_indicators == ("shell", "new") and sup[0].bank_evidence_ref == "B1"
    assert sup[0].evidence_ref == "V1" and sup[1].verified_on is None
    assert [e["row"] for e in err] == [3, 4, 5]
    assert "blank" in err[0]["message"] and "twice" in err[1]["message"]
    assert "YYYY-MM-DD" in err[2]["message"]
    with pytest.raises(InputVatError, match="supplier_id"):
        parse_register_csv(b"name\nx\n")
    with pytest.raises(InputVatError, match="UTF-8"):
        parse_register_csv(b"\xff\xfe\x00bad")


def test_register_row_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.services.input_vat as iv

    monkeypatch.setattr(iv, "MAX_REGISTER_ROWS", 2)
    with pytest.raises(InputVatError, match="more than"):
        parse_register_csv(b"supplier_id\nA\nB\nC\n")


def test_verification_reasons() -> None:
    reg = [Supplier("S1", verified_on=date(2026, 9, 1), bank_evidence_ref="B"),
           Supplier("S2", verified_on=date(2026, 11, 1)),
           Supplier("S3", verified_on=date(2025, 9, 1)),
           Supplier("S4")]
    rows = [_row(1), _row(2, party_id="S2"), _row(3, party_id="S3"), _row(4, party_id="S4"),
            _row(5, party_id="S9"), _row(6, posting_date=date(2026, 9, 30), party_id="S9"),
            _row(7, party_id=None), _row(8, posting_date=None, entry_date=None),
            _row(9, debit=D("-5")), _row(10, vat_amount=D("0"))]
    res = run_input_vat(rows, reg, {}, Params(), today=date(2026, 10, 27))
    uv = {e["party_id"]: e["reason"] for e in _by(res, "unverified_supplier")}
    assert set(uv) == {"S2", "S3", "S4", "S9"}
    assert "verified later" in uv["S2"] and "older than 12 months" in uv["S3"]
    assert "no verification date" in uv["S4"] and "not in the verification" in uv["S9"]
    assert all(e["below_exception_threshold"] for e in _by(res, "unverified_supplier"))
    assert res["effective_date"] == EFF and res["population"]["input_vat_lines"] == 8
    assert any("no supplier ID" in w for w in res["warnings"])
    assert any("no date" in w for w in res["warnings"])
    assert [s["check"] for s in res["summary"]] == list(CHECKS)
    assert res["rules_pending_verification"] is True
    assert "input_vat.verification.effective_date@v1" in res["rule_versions_used"]


def test_spend_threshold_rolling_window_and_risk() -> None:
    reg = [Supplier("S1", verified_on=date(2026, 9, 1), risk_indicators=("new",)),
           Supplier("S2", verified_on=date(2026, 9, 1), bank_evidence_ref="B",
                    risk_indicators=("x",), explanation="ok")]
    # 200k a year before (drops out of the window), then 3 x 150k after the effective date
    rows = [_row(1, posting_date=date(2025, 10, 10), debit=D("200000"), vat_amount=D("1")),
            *[_row(i, posting_date=date(2026, 10, 10 + i), debit=D("150000"),
                   vat_amount=D("1")) for i in (2, 3, 4)],
            *[_row(i, party_id="S2", debit=D("400000")) for i in (5, 6)]]
    res = run_input_vat(rows, reg, {}, Params(), today=date(2026, 10, 27))
    st = _by(res, "spend_threshold")
    assert [(e["party_id"], e["line_ref"]) for e in st] == [("S1", "L004")]
    assert st[0]["rolling_total"] == "450,003.00"
    rk = _by(res, "risk_indicator_unexplained")
    assert [e["party_id"] for e in rk] == ["S1"] and "new" in rk[0]["reason"]
    assert _by(res, "unverified_supplier") == []


def test_employee_expense_and_unmapped() -> None:
    rows = [_row(1, account_code="6050", account_name="Staff transport", party_id=None),
            _row(2, account_code="6050", posting_date=date(2026, 1, 5), party_id=None),
            _row(3, account_code="6100", account_name="Staff welfare", party_id=None),
            _row(4, account_code="6200", account_name="Other", expense_category="parking",
                 vat_amount=D("0")),
            _row(5, account_code="6300", account_name="Employee meals", party_id=None,
                 vat_amount=D("0"))]
    res = run_input_vat(rows, [], {"6050": "transport", "6999": "gym"}, Params(),
                        today=date(2026, 10, 27))
    ee = _by(res, "employee_expense")
    assert [(e["line_ref"], e["before_effective_date"]) for e in ee] == [("L002", True),
                                                                         ("L001", False)]
    cats = {c["category"]: c for c in res["employee_expense_by_category"]}
    assert cats["transport"]["lines"] == 2 and cats["transport"]["vat_amount"] == "100.00"
    assert cats["gym"]["in_rule"] is False
    assert any("gym" in w for w in res["warnings"])
    assert {e["account_code"] for e in _by(res, "staff_cost_unmapped")} == {"6100", "6200"}
    assert "2 employee-expense" in res["conclusion"]


def test_override_shifts_rule_dates() -> None:
    rows = [_row(1, posting_date=date(2025, 10, 5), party_id="S9")]
    res = run_input_vat(rows, [], {}, Params(date(2025, 10, 1)), today=date(2026, 10, 27))
    assert res["effective_date"] == date(2025, 10, 1)
    assert len(_by(res, "unverified_supplier")) == 1
    assert any("TEST-ONLY" in w for w in res["warnings"])
    # without the override the 2025 line is before the effective date
    res2 = run_input_vat(rows, [], {}, Params(), today=date(2026, 10, 27))
    assert _by(res2, "unverified_supplier") == []


def test_missing_effective_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.services.input_vat as iv

    monkeypatch.setattr(iv, "K_EFF", "input_vat.nope")
    with pytest.raises(InputVatError, match="not in the Rules Library"):
        run_input_vat([], [], {}, Params(), today=date(2026, 10, 27))
    res = run_input_vat([], [], {}, Params(date(2025, 1, 1)), today=date(2026, 10, 27))
    assert res["effective_date"] == date(2025, 1, 1)
