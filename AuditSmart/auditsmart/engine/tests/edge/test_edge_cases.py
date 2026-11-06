"""Prompt 3.2 acceptance: edge_cases.csv must produce every expected error (answer key)."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.importer import parse_to_parquet
from app.services.validation import (
    CRITICAL,
    WARNING,
    ValidationReport,
    render_text,
    validate_parquet,
)
from tests.helpers import DATA, answer_key

pytestmark = pytest.mark.edge
SEVERITY = {"Critical": CRITICAL, "High": CRITICAL, "Medium": WARNING, "Low": WARNING}


@pytest.fixture(scope="module")
def report(tmp_path_factory: pytest.TempPathFactory) -> ValidationReport:
    out = tmp_path_factory.mktemp("edge") / "edge.parquet"
    res = parse_to_parquet(DATA / "edge_cases.csv", out, chunk_rows=7)  # force many chunks
    assert res.chunks == 9 and res.rows == 60
    return validate_parquet(out, missing_cols=res.missing_columns)


def _rows_by_code(rep: ValidationReport) -> dict[str, set[int]]:
    out: dict[str, set[int]] = defaultdict(set)
    for i in rep.issues:
        out[i.code] |= set(i.rows)
    return out


def test_every_answer_key_error_is_detected(report: ValidationReport) -> None:
    expected = [r for r in answer_key() if r["file"] == "edge_cases.csv"]
    assert len(expected) == 16
    found = _rows_by_code(report)
    sev = {i.code: i.severity for i in report.issues}
    for exp in expected:
        code, row = exp["error_type"], int(exp["row_no"])
        assert row in found[code], f"{code} not reported for row {row}"
        assert sev[code] == SEVERITY[exp["expected_severity"]]


def test_exact_findings(report: ValidationReport) -> None:
    found = _rows_by_code(report)
    assert found["unbalanced_voucher"] == {1, 2, 3, 4, 5}
    assert found["unreadable_date"] == {6, 8, 10, 12, 14}
    assert found["blank_account"] == {30, 33, 35}
    assert found["duplicate_line_id"] == {38, 40}
    assert found["invalid_trn"] == {44, 47, 50, 53}
    assert found["amount_currency_prefix"] == {28, 29}
    codes = sorted(i.code for i in report.issues)
    assert codes == sorted([
        "unbalanced_voucher", "unbalanced_voucher", "total_out_of_balance",
        "unreadable_date", "unreadable_date", "blank_account", "duplicate_line_id",
        "duplicate_line_id", "amount_currency_prefix", "amount_currency_prefix", "invalid_trn",
    ])
    assert report.critical == 8 and report.warnings == 3 and report.blocked


def test_prompt_example_message_format(report: ValidationReport) -> None:
    ev1 = next(i for i in report.issues if i.code == "unbalanced_voucher" and "EV-001" in i.message)
    assert ev1.message.startswith("Voucher EV-001 is out of balance by AED 0.05")
    assert "rows 1, 2" in ev1.message
    assert ev1.guidance == "Correct the source file or exclude the voucher with a reason."
    ev2 = next(i for i in report.issues if "EV-002" in i.message)
    assert "AED 10.00" in ev2.message and ev2.row_count == 3
    total = next(i for i in report.issues if i.code == "total_out_of_balance")
    assert "AED 10.05" in total.message


def test_valid_edge_formats_parse_without_errors(report: ValidationReport) -> None:
    flagged = set().union(*(set(i.rows) for i in report.issues))
    # dd/mm/yyyy (16-17), Excel serial (18-19), commas (20-21), brackets (23), trailing minus (26)
    assert not flagged & {16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 41}
    assert report.total_dr - report.total_cr == Decimal("10.05")


def test_plain_english_listing(report: ValidationReport) -> None:
    text = render_text(report)
    assert text.count("How to fix:") == len(report.issues)
    assert "row 1 is the first row under the header" in text
    assert "stay blocked" in text


def test_every_issue_has_guidance_and_rows_capped(report: ValidationReport, tmp_path: Path) -> None:
    for i in report.issues:
        assert i.message and i.guidance and i.severity in (CRITICAL, WARNING)
        assert len(i.rows) <= 50
