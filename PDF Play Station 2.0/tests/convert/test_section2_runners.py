"""Section 2 tool pages -> copied PDF Converter Pro engine (app/runners.py)."""

from pathlib import Path

import pytest
from docx import Document
from openpyxl import load_workbook

from app import runners
from app.services.common import Job, UserError
from convert_helpers import tesseract_available

ROOT = Path(__file__).resolve().parents[2]


def opts(**over):
    base = {"Worksheets": "Combine continued tables", "Word mode": "Editable document",
            "Indian number format (1,00,000)": True, "OCR for scanned pages": "Off", "OCR language": "English",
            "Pages": "", "One workbook for all PDFs": False}
    base.update(over)
    return base


def test_pdf_to_excel_next_to_source(pdfs, tmp_path):
    src = tmp_path / "Ledger.pdf"
    src.write_bytes(pdfs["table"].read_bytes())
    r = runners.to_excel(Job(), [str(src)], opts(), "", {})
    assert r["files"] == [str(tmp_path / "Ledger.xlsx")]
    wb = load_workbook(r["files"][0])
    assert any(ws.max_row > 2 for ws in wb.worksheets)
    assert "table(s)" in r["details"][0]
    again = runners.to_excel(Job(), [str(src)], opts(), "", {})          # never overwrites
    assert again["files"] == [str(tmp_path / "Ledger (2).xlsx")]


def test_pdf_to_word_and_both(pdfs, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    r = runners.to_word(Job(), [str(pdfs["simple"])], opts(), str(out), {})
    assert r["files"][0].endswith(".docx") and Document(r["files"][0]).paragraphs
    r = runners.to_both(Job(), [str(pdfs["table"])], opts(), str(out), {})
    assert sorted(Path(f).suffix for f in r["files"]) == [".docx", ".xlsx"]


def test_combined_workbook_and_failure_isolation(pdfs, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    files = [str(pdfs["table"]), str(pdfs["corrupt"]), str(pdfs["multipage"])]
    r = runners.to_excel(Job(), files, opts(**{"One workbook for all PDFs": True}),
                         str(out), {})
    assert len([f for f in r["files"] if f.endswith(".xlsx")]) == 1
    assert "2 of 3" in r["message"] and any("corrupt.pdf" in w for w in r["warnings"])


def test_password_and_page_range(pdfs, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    enc = str(pdfs["encrypted"])
    with pytest.raises(UserError):
        runners.to_word(Job(), [enc], opts(), str(out), {})
    r = runners.to_word(Job(), [enc], opts(), str(out), {enc: "secret123"})
    assert "Confidential" in " ".join(p.text for p in Document(r["files"][0]).paragraphs)
    with pytest.raises(UserError):
        runners.to_excel(Job(), [str(pdfs["table"])], opts(Pages="5-2"), str(out), {})


def test_bank_statement_selftest_file(tmp_path):
    """The statement PDF Converter Pro's self-test used: 21 rows, none flagged."""
    src = tmp_path / "statement.pdf"
    src.write_bytes((ROOT / "assets" / "selftest_statement.pdf").read_bytes())
    r = runners.bank(Job(), [str(src)], opts(**{"OCR for scanned pages": "Automatic (recommended)"}), "", {})
    assert "21 transactions" in r["details"][0] and "every row proven" in r["details"][0]
    wb = load_workbook(r["files"][0])
    assert {"Statement", "Review"} <= set(wb.sheetnames)
    assert len(r["warnings"]) == len(set(r["warnings"]))


@pytest.mark.skipif(not tesseract_available(), reason="Tesseract not installed")
def test_scanned_pdf_to_excel_uses_ocr(pdfs, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    r = runners.to_excel(Job(), [str(pdfs["scanned"])], opts(**{"OCR for scanned pages": "Automatic (recommended)"}),
                         str(out), {})
    assert "read with OCR" in r["details"][0]


def test_conversion_cancels(pdfs, tmp_path):
    from app.jobs import run_function
    status, _ = run_function(runners.to_excel, {"files": [str(pdfs["table"])], "opts": opts(),
                                                "out_dir": str(tmp_path), "passwords": {}},
                             lambda *a: None, lambda: True)
    assert status == "cancelled"
    assert not list(tmp_path.glob("*.xlsx"))
