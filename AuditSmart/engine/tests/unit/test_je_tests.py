"""JE criteria on hand-built lines (prompt 3.4)."""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal
from typing import Any

import pytest

from app.services import calendar as c
from app.services import je_tests as je

CAL = c.CalendarProfile(
    weeks=(c.WorkWeek(frozenset({6, 7}), date(2022, 1, 1), half_days={5: time(12, 0)}),),
    holidays=(c.HolidayDay(date(2025, 6, 5), "Arafat Day"),),
)
FYE = date(2025, 12, 31)


def _row(n: int, v: str, d: date | None, dr: str = "0", cr: str = "0", **kw: Any) -> dict[str, Any]:
    r: dict[str, Any] = {
        "row_no": n,
        "line_id": f"T{n:03d}",
        "voucher_no": v,
        "posting_date": d,
        "posting_time": "10:00:00",
        "account_code": "5010",
        "account_type": "Expense",
        "narration": "Purchase of goods",
        "user_id": "U1",
        "party_id": "",
        "invoice_no": "",
        "debit": Decimal(dr),
        "credit": Decimal(cr),
    }
    r.update(kw)
    return r


def _pair(n: int, v: str, d: date | None, amt: str, **kw: Any) -> list[dict[str, Any]]:
    return [
        _row(n, v, d, dr=amt, **kw),
        _row(n + 1, v, d, cr=amt, account_code="2010", account_type="Liability"),
    ]


def _base(k: int = 20) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for i in range(k):
        rows += _pair(1000 + 2 * i, f"PI-{i + 1:03d}", date(2025, 3, 3), f"{1234 + i}.56")
    return rows


def _run(rows: list[dict[str, Any]], **ov: Any) -> dict[str, Any]:
    return je.run_je_tests(rows, je.JeParams.build(FYE, ov), CAL, dataset_hash="h")


def _flags(res: dict[str, Any]) -> dict[str, list[str]]:
    return {f["line_ref"]: f["flags"] for f in res["flags"]}


def test_each_criterion() -> None:
    rows = _base()
    rows += _pair(1, "PV-001", date(2025, 3, 8), "1500.25")  # Saturday
    rows += _pair(3, "PV-002", date(2025, 6, 5), "1500.35")  # holiday
    rows += _pair(5, "PV-003", date(2025, 3, 7), "1500.45", posting_time="15:30:00")  # Fri
    rows += _pair(7, "PV-004", date(2025, 3, 7), "1500.55", posting_time="11:59:59")  # ok
    rows += _pair(9, "PV-005", date(2025, 3, 4), "20000")  # round
    rows += _pair(11, "PV-006", date(2025, 3, 4), "9000")  # < min: not round
    rows += _pair(13, "JV-007", date(2025, 12, 27), "1500.65", user_id="FINMGR")
    rows += _pair(15, "PV-008", date(2025, 3, 4), "1500.75", narration="  Misc. ")
    rows += _pair(17, "PV-009", date(2025, 3, 4), "1500.85", narration="")
    rows += [
        _row(
            19, "JV-010", date(2025, 3, 4), dr="99.10", account_code="4010", account_type="Revenue"
        ),
        _row(20, "JV-010", date(2025, 3, 4), cr="99.00", account_code="1010", account_type="Asset"),
    ]
    rows += _pair(21, "PI-100", date(2025, 3, 4), "700.10", party_id="s1", invoice_no="inv1")
    rows += _pair(23, "PI-101", date(2025, 3, 20), "700.10", party_id="S1", invoice_no="INV1")
    rows += _pair(25, "PI-102", date(2025, 3, 21), "800.10", party_id="S2", invoice_no="A")
    rows += _pair(27, "PI-103", date(2025, 3, 21), "800.10", party_id="S2", invoice_no="B")
    rows += [_row(29, "XX-1", None, dr="5.00", posting_time="bad")]
    res = _run(
        rows, senior_users=["finmgr"], large_amount="15000", sensitive_account_codes=["1010"]
    )
    f = _flags(res)
    assert "non_working_day" in f["T001"] and "non_working_day" in f["T003"]
    assert {x["non_working_reason"] for x in res["flags"] if x["line_ref"] in ("T001", "T003")} == {
        "weekend",
        "holiday",
    }
    assert f["T005"] == ["after_half_day_cutoff"] and "T007" not in f
    assert "round_sum" in f["T009"] and "large_amount" in f["T009"]
    assert "T011" not in f
    assert {"period_end", "senior_user"} <= set(f["T013"])
    assert f["T015"] == ["vague_narration"] and f["T017"] == ["vague_narration"]
    assert {"manual_sensitive", "unbalanced_voucher", "unusual_account_pair"} <= set(f["T019"])
    assert "manual_sensitive" in f["T020"]
    assert "duplicate_invoice" in f["T023"] and "T021" not in f
    dup = next(x for x in res["flags"] if x["line_ref"] == "T023")
    assert dup["related_line"] == "T021"
    assert "duplicate_party_amount_date" in f["T027"] and "T025" not in f
    assert res["population"]["lines_without_date"] == 1
    assert any(g["series"] == "PI-" for g in res["sequence_gaps"])
    summ = {s["test"]: s for s in res["summary"]}
    assert summ["round_sum"]["lines"] == 2 and summ["round_sum"]["vouchers"] == 1
    assert summ["round_sum"]["value"] == "40,000.00"
    assert res["calendar_hash"] and res["rules_pending_verification"] is True
    assert res["engine_version"].startswith("auditsmart-engine ")
    assert res["parameters"]["sources"]["round_min"] == "je.round_sum.min@v1"
    assert res["parameters"]["sources"]["senior_users"] == "override"


def test_rare_user_and_scoring_selection() -> None:
    rows = _base(120)
    rows += _pair(
        1, "PV-001", date(2025, 3, 8), "50000", user_id="RARE", narration="adj"
    )  # weekend + round + rare + vague = 4
    rows += _pair(3, "PV-002", date(2025, 3, 9), "1500.11", narration="error")  # 2
    res = _run(rows)
    top = res["flags"][0]
    assert top["line_ref"] == "T001" and top["risk_score"] == 4 and top["selection"] == "test"
    assert "rare_user" in top["flags"]
    t3 = next(x for x in res["flags"] if x["line_ref"] == "T003")
    assert t3["risk_score"] == 2 and t3["selection"] == "test_topup"
    assert res["selected_for_testing"] >= 2
    res2 = _run(rows, judgement_min_items=0)
    t3 = next(x for x in res2["flags"] if x["line_ref"] == "T003")
    assert t3["selection"] == "judgement"


def test_test_subset_and_errors() -> None:
    rows = _base() + _pair(1, "PV-001", date(2025, 3, 8), "50000")
    res = _run(rows, tests=["round_sum"])
    assert [x["flags"] for x in res["flags"]] == [["round_sum"], ["round_sum"]]
    assert next(s for s in res["summary"] if s["test"] == "non_working_day")["enabled"] is False
    with pytest.raises(je.JeTestError, match="Unknown JE test"):
        je.JeParams.build(FYE, {"tests": ["nope"]})
    with pytest.raises(je.JeTestError, match="Unknown JE parameter"):
        je.JeParams.build(FYE, {"colour": 1})
    with pytest.raises(je.JeTestError, match="positive"):
        je.JeParams.build(FYE, {"round_multiple": "0"})
    with pytest.raises(je.JeTestError, match="no lines"):
        _run([])
    with pytest.raises(je.JeTestError, match="Rules Library"):
        je.JeParams.build(date(2000, 1, 1))


def test_calendar_gap_reported_not_crashing() -> None:
    cal = c.CalendarProfile(weeks=(c.WorkWeek(frozenset({6, 7}), date(2025, 1, 1)),))
    rows = _pair(1, "PV-001", date(2024, 12, 28), "100.10") + _base()
    res = je.run_je_tests(
        rows, je.JeParams.build(FYE), c.ResolvedCalendar(cal, date(2025, 1, 1), date(2025, 12, 31))
    )
    assert res["calendar_errors"] and "No work week" in res["calendar_errors"][0]
    res2 = je.run_je_tests(_base(), je.JeParams.build(None), cal)
    assert res2["calendar"]["start"] == "2025-03-03"
    res3 = je.run_je_tests([_row(1, "A-1", None, dr="1")], je.JeParams.build(None), cal)
    assert res3["population"]["lines_without_date"] == 1


def test_time_parser() -> None:
    assert je._time("9:05") == time(9, 5) and je._time(time(1, 2)) == time(1, 2)
    assert je._time("25:00:00") is None and je._time("") is None and je._time(None) is None
