from datetime import datetime
from pathlib import Path

import pytest
from openpyxl import load_workbook

from app.convert.batch import BatchProcessor
from app.convert.cell_values import parse_cell
from app.convert.models import DocumentContent, PageContent, TableData
from app.convert.pdf_to_excel import build_workbook
from app.convert.settings import ConversionSettings


def convert(paths, settings, ocr):
    return BatchProcessor(list(paths), settings, ocr).run()


def sheet_rows(ws):
    return [[c.value for c in row] for row in ws.iter_rows()]


# ------------------------------------------------------------ cell typing

@pytest.mark.parametrize("text, value, fmt", [
    ("1,234.50", 1234.5, "#,##0.00"),
    ("-450.10", -450.1, "0.00"),
    ("(1,200.00)", -1200, "#,##0.00_);(#,##0.00)"),
    ("12.5%", 0.125, "0.0%"),
    ("-3.25%", -0.0325, "0.00%"),
    ("0", 0, None),
    ("2024", 2024, None),
    ("−1,000", -1000, "#,##0"),           # Unicode minus sign
])
def test_numbers_are_converted_exactly(text, value, fmt):
    parsed = parse_cell(text)
    assert parsed.is_numeric
    assert parsed.value == pytest.approx(value) and type(parsed.value) in (int, float)
    assert parsed.number_format == fmt


def test_indian_grouping():
    parsed = parse_cell("1,25,000.50")
    assert parsed.value == 125000.5 and "##\\,##" in parsed.number_format
    assert parse_cell("1,25,000.50", indian_format=False).number_format == "#,##0.00"


@pytest.mark.parametrize("text", [
    "000123",                 # leading zeros
    "123456789012",           # account number
    "ABCDE1234F",             # PAN
    "27ABCDE1234F1Z5",        # GSTIN
    "1,23,4",                 # malformed grouping
    "Rs. 500",                # currency prefix kept as written
    "1,234.00 Dr",
    "31/02/2024",             # impossible date
    "12/03/24",               # 2-digit year is ambiguous
    "1234567890123456.5",     # beyond Excel precision
    "=SUM(A1:A2)",            # must never become a formula
])
def test_identifiers_and_ambiguous_values_stay_text(text):
    parsed = parse_cell(text)
    assert isinstance(parsed.value, str) and parsed.value == text.strip()


def test_dates_are_day_first():
    assert parse_cell("05/04/2024").value == datetime(2024, 4, 5)
    assert parse_cell("31-Mar-2025").value == datetime(2025, 3, 31)
    assert parse_cell("05/04/2024", convert_dates=False).value == "05/04/2024"


def test_blank_is_not_zero():
    assert parse_cell("").value is None and parse_cell(None).value is None
    assert parse_cell("0").value == 0


# ------------------------------------------------------------ workbook output

def test_table_pdf_values(pdfs, settings, no_ocr):
    settings.output_format = "excel"
    summary = convert([pdfs["table"]], settings, no_ocr)
    res = summary.results[0]
    assert res.status == "success", res.error
    wb = load_workbook(res.outputs[0])
    assert wb.sheetnames[0] == "Table_001" and "Conversion_Notes" in wb.sheetnames
    ws = wb["Table_001"]
    rows = sheet_rows(ws)
    assert rows[0] == ["Source Page", "Particulars", "Account No", "Amount", "Change", "Date"]
    assert ws["B1"].font.bold and ws.freeze_panes == "A2" and ws.auto_filter.ref
    by_name = {r[1]: r for r in rows[1:]}
    assert by_name["Opening balance"][2:6] == ["000123", 125000.5, 0.125, datetime(2024, 4, 1)]
    assert by_name["Interest earned"][3] == 2345.75 and by_name["Interest earned"][4] == pytest.approx(-0.0325)
    assert by_name["Bank charges"][3] == -1200
    assert by_name["Refund"][2] == "123456789012" and by_name["Refund"][3] == -450.1
    pan_row = by_name["PAN ABCDE1234F"]
    assert pan_row[2] == "27ABCDE1234F1Z5" and pan_row[3] == 0 and pan_row[4] is None
    assert pan_row[5] == "31/02/2024"
    assert all(r[0] == 1 for r in rows[1:])     # source page references


def test_multipage_table_combined(pdfs, settings, no_ocr):
    settings.output_format = "excel"
    res = convert([pdfs["multipage"]], settings, no_ocr).results[0]
    wb = load_workbook(res.outputs[0])
    tables = [s for s in wb.sheetnames if s.startswith("Table_")]
    assert tables == ["Table_001"]
    rows = sheet_rows(wb["Table_001"])
    assert rows[0] == ["Source Page", "Sr", "Description", "Debit", "Credit"]
    body = rows[1:]
    assert len(body) == 120                                # header repeated on each page was dropped
    assert [r[1] for r in body] == list(range(1, 121))
    assert body[-1][3] == 1200 and body[-1][4] == 360.5
    assert len({r[0] for r in body}) >= 3                   # rows keep their own page numbers


def test_multipage_table_separate_sheets(pdfs, settings, no_ocr):
    settings.output_format = "excel"
    settings.sheet_mode = "per_table"
    res = convert([pdfs["multipage"]], settings, no_ocr).results[0]
    wb = load_workbook(res.outputs[0])
    assert len([s for s in wb.sheetnames if s.startswith("Table_")]) >= 3


def test_per_page_sheets(pdfs, settings, no_ocr):
    settings.output_format = "excel"
    settings.sheet_mode = "per_page"
    res = convert([pdfs["multipage"]], settings, no_ocr).results[0]
    wb = load_workbook(res.outputs[0])
    assert wb.sheetnames[:2] == ["Page_001", "Page_002"]


def test_borderless_table_detected(pdfs, settings, no_ocr):
    settings.output_format = "excel"
    res = convert([pdfs["borderless"]], settings, no_ocr).results[0]
    rows = sheet_rows(load_workbook(res.outputs[0])["Table_001"])
    assert rows[0] == ["Source Page", "Date", "Narration", "Debit", "Credit", "Balance"]
    assert rows[2][1:] == [datetime(2024, 4, 2), "NEFT ACME LTD", None, 5000, 15000]
    assert rows[4][1:] == [datetime(2024, 4, 9), "CHQ 000456", 1234.56, None, 11265.44]


@pytest.mark.parametrize("kind, ncols, nrows", [("ruled", 22, 60), ("borderless", 24, 30)])
def test_wide_tables_keep_every_column(tmp_path, settings, no_ocr, kind, ncols, nrows):
    import pdf_factory
    from docx import Document
    maker = pdf_factory.wide_ruled_pdf if kind == "ruled" else pdf_factory.wide_borderless_pdf
    pdf = maker(tmp_path / f"wide_{kind}.pdf", ncols, nrows)
    res = convert([pdf], settings, no_ocr).results[0]
    wb = load_workbook([p for p in res.outputs if p.suffix == ".xlsx"][0])
    assert [s for s in wb.sheetnames if s.startswith("Table_")] == ["Table_001"]
    got = [r[1:] for r in sheet_rows(wb["Table_001"])]          # drop Source Page
    expected = pdf_factory.wide_rows(ncols, nrows)
    assert got[0] == expected[0] and len(got) == len(expected)
    for g_row, e_row in zip(got[1:], expected[1:]):
        assert g_row[0] == e_row[0]
        for g, e in zip(g_row[1:], e_row[1:]):
            negative = e.startswith("(")
            assert g == pytest.approx(float(e.strip("()").replace(",", "")) * (-1 if negative else 1))
    doc = Document(str([p for p in res.outputs if p.suffix == ".docx"][0]))
    assert all(len(t.columns) == ncols for t in doc.tables)


def test_no_tables_exports_text(pdfs, settings, no_ocr):
    settings.output_format = "excel"
    res = convert([pdfs["simple"]], settings, no_ocr).results[0]
    assert res.status == "warning" and any("no tables" in w for w in res.warnings)
    wb = load_workbook(res.outputs[0])
    assert wb.sheetnames == ["Extracted_Text", "Conversion_Notes"]
    rows = sheet_rows(wb["Extracted_Text"])
    assert rows[0] == ["Page Number", "Block", "Type", "Extracted Text", "Source"]
    texts = [r[3] for r in rows[1:]]
    assert "Annual Compliance Note" in texts
    assert any("bold words, italic words" in t for t in texts)


def test_combined_workbook(pdfs, settings, no_ocr):
    settings.output_format = "excel"
    settings.workbook_mode = "combined"
    summary = convert([pdfs["table"], pdfs["borderless"]], settings, no_ocr)
    assert summary.combined_output is not None
    wb = load_workbook(summary.combined_output)
    assert wb.sheetnames == ["table", "borderless", "Conversion_Notes"]
    assert all(summary.combined_output in r.outputs for r in summary.results)


def test_formula_like_text_is_stored_as_text(tmp_path):
    table = TableData(rows=[["Name", "Formula"], ["x", "=1+1"], ["y", "@cmd"]], pages=[1], row_pages=[1, 1, 1],
                      header_rows=1)
    page = PageContent(1, 595, 842, items=[table])
    doc = DocumentContent(Path("t.pdf"), 1, [page])
    wb, _ = build_workbook([doc], ConversionSettings(include_page_refs=False))
    cell = wb["Table_001"]["B2"]
    assert cell.value == "=1+1" and cell.data_type == "s"
    path = tmp_path / "f.xlsx"
    wb.save(path)
    assert load_workbook(path)["Table_001"]["B2"].value == "=1+1"
