"""Bank-statement mode: parsing, balance reconciliation, extraction and Excel output.

Real-OCR tests run only when Tesseract is installed; everything else runs offline
on synthetic statements (no real customer data).
"""

from decimal import Decimal as D
from pathlib import Path

import pytest
from openpyxl import load_workbook

import pdf_factory
from app.convert.bank_statement import (StatementRow, check_dates, extract_statement, parse_amount, parse_balance,
                                reconcile)
from app.convert.batch import BatchProcessor
from app.convert.ocr_engine import OcrEngine
from convert_helpers import tesseract_available


def row(date, w, d, b, kind="txn"):
    return StatementRow(page=1, y=0, kind=kind, date_text=date,
                        withdrawal=D(w) if w else None, deposit=D(d) if d else None,
                        balance=D(b) if b else None)


# ------------------------------------------------------------ parsing

@pytest.mark.parametrize("text, value", [
    ("1,25,000.50Cr", "125000.50"), ("..44,713.00Cr", "44713.00"), ("2,49, 641.16Cr", "249641.16"),
    ("17.70", "17.70"), ("0.00", "0.00"), ("10,00,000.00", "1000000.00"),
])
def test_parse_amounts(text, value):
    assert parse_balance(text) == D(value)


def test_parse_rejects_malformed_and_handles_dr():
    assert parse_amount("0,05,653.16") is None                # malformed grouping (lost leading digit): rejected
    assert parse_balance("1,234.00Dr") == D("-1234.00")
    assert parse_balance("20,000.00 1,69,740.16Cr") == D("169740.16")   # right-most amount is the balance
    assert parse_amount("GST") is None


# ------------------------------------------------------------ reconciliation rules

def test_all_rows_balance():
    rows = [row("", None, "100.00", "100.00", "bf"), row("01-04-2020", "40.00", None, "60.00"),
            row("02-04-2020", None, "15.50", "75.50")]
    reconcile(rows)
    assert [r.status for r in rows] == ["OK", "OK", "OK"]


def test_misread_balance_is_inferred_from_amounts_and_next_row():
    rows = [row("", None, "100.00", "100.00", "bf"), row("01-04-2020", "40.00", None, "80.00"),
            row("02-04-2020", None, "10.00", "70.00")]
    reconcile(rows)
    assert rows[1].balance == D("60.00") and rows[1].status == "Inferred"
    assert rows[2].status == "OK"


def test_missing_amount_is_inferred_from_balances():
    rows = [row("", None, "100.00", "100.00", "bf"), row("01-04-2020", None, None, "60.00"),
            row("02-04-2020", None, "10.00", "70.00")]
    reconcile(rows)
    assert rows[1].withdrawal == D("40.00") and rows[1].deposit is None and rows[1].status == "Inferred"


def test_amount_in_wrong_column_is_corrected():
    rows = [row("", None, "100.00", "100.00", "bf"), row("01-04-2020", None, "40.00", "60.00"),
            row("02-04-2020", None, "10.00", "70.00")]
    reconcile(rows)
    assert rows[1].withdrawal == D("40.00") and rows[1].deposit is None and rows[1].status == "Corrected"


def test_consistent_misreads_are_never_ok():
    """Two neighbouring balances with the same spurious leading digit agree with
    each other; the chain of trust must keep them flagged."""
    rows = [row("", None, "100.00", "100.00", "bf"), row("01-04-2020", None, "50.00", "150.00"),
            row("02-04-2020", None, "70.00", "4220.00"),         # truly 220.00 - stray '4' read in front
            row("03-04-2020", "20.00", None, "4200.00"),         # truly 200.00 - same stray digit
            row("04-04-2020", None, "5.00", "205.00")]
    reconcile(rows)
    assert rows[2].status != "OK" and rows[3].status != "OK"
    assert rows[4].balance == D("205.00")


def test_unproven_rows_are_check():
    rows = [row("", None, "100.00", "100.00", "bf"), row("01-04-2020", "40.00", None, "61.00"),
            row("02-04-2020", None, "10.00", "99.00")]
    reconcile(rows)
    assert rows[1].status == "Check" or rows[2].status == "Check"


def test_dates_out_of_order_or_invalid_are_flagged():
    rows = [row("01-04-2020", "1.00", None, "1.00"), row("34-04-2020", "1.00", None, "1.00"),
            row("19-04-2020", "1.00", None, "1.00"), row("17-04-2020", "1.00", None, "1.00")]
    for r in rows:
        r.status = "OK"
    check_dates(rows)
    assert rows[1].status == "Check" and rows[2].status == "Check"


# ------------------------------------------------------------ extraction

@pytest.fixture(scope="module")
def statement(tmp_path_factory):
    d = tmp_path_factory.mktemp("stmt")
    truth = pdf_factory.statement_transactions()
    pdf = pdf_factory.bank_statement_pdf(d / "statement.pdf", truth)
    return truth, pdf, d


def _compare(truth, result):
    """Align extracted rows with the truth by (date, balance) so that one missed
    row does not shift every later comparison; count exact rows and rows that
    are wrong yet presented as verified (silent errors)."""
    from difflib import SequenceMatcher
    expected = [(D(f"{t[3]:.2f}") if t[3] is not None and t[0] else None,
                 D(f"{t[4]:.2f}") if t[4] is not None else None, D(f"{t[5]:.2f}")) for t in truth]
    tk = [(t[0], e[2]) for t, e in zip(truth, expected)]
    gk = [(r.date_text, r.balance) for r in result.rows]
    exact = silent = 0
    matched = set()
    for op, i1, i2, j1, j2 in SequenceMatcher(None, tk, gk, autojunk=False).get_opcodes():
        if op not in ("equal", "replace"):
            continue
        for ti, gi in zip(range(i1, i2), range(j1, j2)):
            matched.add(gi)
            r = result.rows[gi]
            if (r.withdrawal, r.deposit, r.balance) == expected[ti] and r.date_text == truth[ti][0]:
                exact += 1
            elif r.status in ("OK", "Re-read", "Corrected"):
                silent += 1
    # extra rows that match nothing must not be presented as verified either
    silent += sum(1 for gi, r in enumerate(result.rows)
                  if gi not in matched and r.status in ("OK", "Re-read", "Corrected"))
    return exact, silent


def test_text_statement_exact(statement):
    truth, pdf, _ = statement
    res = extract_statement(pdf, OcrEngine(), [1, 2])
    assert res.method == "text"
    assert len(res.rows) == len(truth)
    exact, silent = _compare(truth, res)
    assert exact == len(truth) and silent == 0
    assert all(r.status == "OK" for r in res.rows)
    assert res.checkpoints and all(c.matches for c in res.checkpoints)
    assert res.rows[1].particulars and res.rows[0].kind == "bf"


def test_not_a_statement_raises(pdfs):
    from app.convert.bank_statement import StatementError
    with pytest.raises(StatementError):
        extract_statement(pdfs["simple"], OcrEngine(), [1])


@pytest.mark.skipif(not tesseract_available(), reason="Tesseract OCR is not installed on this machine")
def test_scanned_statement_has_no_silent_errors(statement):
    truth, pdf, d = statement
    scan = pdf_factory.scanned_copy(pdf, d / "scanned_statement.pdf")
    res = extract_statement(scan, OcrEngine(), [1, 2])
    assert res.method == "ocr"
    exact, silent = _compare(truth, res)
    assert silent == 0, "a wrong value must never be presented as verified"
    # Deliberately harsh page (7.5 pt text, 17 pt rows, speckle noise, amounts
    # offset from their descriptions). Real scans tested during development did
    # better (32/32 and 241/251 exact); rows not exact here are all flagged.
    assert exact >= 0.75 * len(truth), f"only {exact}/{len(truth)} rows exact"


# ------------------------------------------------------------ batch + workbook

def test_bank_mode_workbook(statement, settings, no_ocr):
    truth, pdf, _ = statement
    settings.output_format = "excel"
    settings.document_type = "bank_statement"
    res = BatchProcessor([pdf], settings, no_ocr).run().results[0]
    assert res.status == "success", (res.error, res.warnings)
    assert res.statement_rows == len(truth)
    wb = load_workbook(res.outputs[0])
    assert wb.sheetnames == ["Statement", "Review", "Bank Totals Check", "Notes"]
    ws = wb["Statement"]
    header = [c.value for c in ws[5]]
    assert header[:8] == ["Sr", "Date", "Particulars", "Additional details", "Chq No", "Withdrawals",
                          "Deposits", "Balance"]
    assert ws.cell(row=6, column=8).value == pytest.approx(truth[0][5])
    assert str(ws.cell(row=7, column=14).value).startswith("=ROUND(")
    assert wb["Review"].cell(row=4, column=1).value.startswith("None")
    assert {r[9] for r in wb["Bank Totals Check"].iter_rows(min_row=4, max_row=5, values_only=True)} == {"Match"}


def test_bank_mode_falls_back_for_ordinary_documents(pdfs, settings, no_ocr):
    settings.output_format = "excel"
    settings.document_type = "bank_statement"
    res = BatchProcessor([pdfs["table"]], settings, no_ocr).run().results[0]
    assert res.status == "warning" and any("general document" in w for w in res.warnings)
    assert "Table_001" in load_workbook(res.outputs[0]).sheetnames
