"""Prompt 3.6 unit tests: workpaper builder variants and the STALE / AI-draft gate."""

from __future__ import annotations

import io
from typing import Any

import pytest
from openpyxl import load_workbook

from app.services.workpaper import (
    SHEETS,
    WorkpaperData,
    WorkpaperError,
    _num,
    _txt,
    build_workbook,
    check_gate,
    rule_rows,
)


def _wb(**kw: Any) -> Any:
    return load_workbook(io.BytesIO(build_workbook(WorkpaperData(
        wp_ref="T-1", engagement={"client_name": "Dummy Co", "fye": "2025-12-31"}, **kw))))


def test_empty_workpaper_has_every_sheet() -> None:
    wb = _wb()
    assert wb.sheetnames == list(SHEETS)
    assert "No sample" in wb["Sampling"]["A4"].value
    assert wb["Sample & Testing"]["A4"].value == "No sample items."
    assert "No JE testing" in wb["JE Risk"]["A4"].value
    assert wb["Benford"]["A4"].value == "No Benford analysis is included."
    assert "not been evaluated" in wb["Evaluation"]["A4"].value
    cal = [r for r in wb["Rules & Calendar"].iter_rows(values_only=True) if r[0]]
    assert any("No calendar" in str(r[0]) for r in cal)
    assert wb["Lead"].cell(17, 2).value == "Not included"


def test_ratio_input_vat_and_benford_error() -> None:
    sample = {"method": "stratified", "sample_size": 3, "rules_pending_verification": True,
              "warnings": ["w1"],
              "evaluation": {"method": "ratio", "projected_misstatement": "10.00",
                             "actual_misstatement_key_items": "0.00",
                             "tolerable_misstatement": "100", "conclusion": "Acceptable",
                             "strata": [{"stratum": 1, "sample_items": 3, "sample_book": "9",
                                         "sample_misstatement": "1",
                                         "population_value": "90", "projected": "10"}],
                             "warnings": ["D16 note"]}}
    iv = {"input_vat_run_id": "iv1", "conclusion": "3 exceptions", "basis": "Decision 13",
          "summary": [{"check": "unverified_supplier", "lines": 2, "value": "1,000.00"}],
          "exceptions": [{"line_ref": "L1", "check": "unverified_supplier", "party_id": "S1",
                          "amount": "500", "reason": "not in register"}],
          "rule_versions_used": {"x@v1": {"rule_key": "x", "ref": "x@v1", "version": 1,
                                          "value": 1, "status": "approved",
                                          "source_url": "https://example.invalid/x"}}}
    wb = _wb(sample=sample, input_vat=iv, je={"benford": {"error": "No amounts"}},
             ai_drafts=[{"line_ref": "L1", "ai_generated": False, "text": "manual note"}])
    ev = list(wb["Evaluation"].iter_rows(values_only=True))
    assert ev[3][:2] == ("Projected misstatement", 10.0)
    assert any(r[0] == 1 and r[5] == 10.0 for r in ev)
    assert wb["Benford"]["A4"].value == "No amounts"
    ivr = list(wb["Input VAT"].iter_rows(values_only=True))
    assert any(r[0] == "unverified_supplier" and r[2] == 1000.0 for r in ivr)
    assert any(r[0] == "L1" and r[4] == "not in register" for r in ivr)
    d = next(r for r in wb["AI Drafts"].iter_rows(values_only=True) if r[0] == "L1")
    assert d[1] == "Manual" and d[5] == "✗"
    rc = next(r for r in wb["Rules & Calendar"].iter_rows(values_only=True) if r[0] == "x")
    assert rc[6] == "https://example.invalid/x" and rc[4] == "input_vat"
    lead = list(wb["Lead"].iter_rows(values_only=True))
    assert any(r[0] and "pending verification" in str(r[0]) for r in lead)
    assert next(r for r in lead if r[0] == "Evaluation")[1] == "Projected 10.00"


def test_rule_rows_merges_sources() -> None:
    used = {"a": {"ref": "a@v1", "version": 1, "value": "1", "status": "s"}, "bad": "x"}
    rows = rule_rows({"_name": "one", "rule_versions_used": used},
                     {"_name": "two", "rule_versions_used": used,
                      "benford": {"rule_versions_used": used}}, None)
    assert len(rows) == 1 and rows[0]["used_by"] == ["one", "two", "two/benford"]


def test_cell_helpers() -> None:
    assert _num(None) is None and _num(True) == "Yes" and _num(3) == 3
    assert _num("1,234.50") == 1234.5 and _num("abc") == "abc"
    assert _txt(None) == "" and _txt(False) == "No" and _txt([1, 2]) == "1, 2"
    assert _txt({"a": [1]}) == "a: 1"


def test_gate() -> None:
    res = [{"kind": "sample", "id": "s1", "status": "current"},
           {"kind": "je_run", "id": "j1", "status": "STALE"}]
    with pytest.raises(WorkpaperError) as e:
        check_gate(res, [], [], "Manager")
    assert e.value.status_code == 409
    ok = {"kind": "je_run", "id": "j1", "justification": "x" * 20}
    assert check_gate(res, [], [ok], "Partner") == [ok]
    with pytest.raises(WorkpaperError) as e:
        check_gate(res, [], [ok], "Staff")
    assert e.value.status_code == 403
    with pytest.raises(WorkpaperError) as e:
        check_gate(res[:1], [{"ai_generated": True, "line_ref": "L9"}], [], "Manager")
    assert e.value.status_code == 409 and "L9" in e.value.message
    assert check_gate(res[:1], [{"ai_generated": True, "reviewed_by": "u"}], [], None) == []
