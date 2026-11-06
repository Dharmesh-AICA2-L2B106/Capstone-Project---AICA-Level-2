from __future__ import annotations

import io
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import openpyxl
import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.services.importer import (
    copy_stream,
    missing_columns,
    norm_header,
    parse_amount,
    parse_date,
    parse_to_parquet,
    read_headers,
    read_parquet_rows,
    suggest_mapping,
    to_csv_bytes,
)
from app.services.validation import validate_parquet


@pytest.mark.parametrize(("raw", "expected"), [
    ("2025-03-15", date(2025, 3, 15)), ("2025-03-15 10:20:00", date(2025, 3, 15)),
    ("2025-03-15T10:20", date(2025, 3, 15)), ("15/03/2025", date(2025, 3, 15)),
    ("5/3/2025", date(2025, 3, 5)), ("15-03-2025", date(2025, 3, 15)),
    ("15.03.2025", date(2025, 3, 15)), ("15-Mar-2025", date(2025, 3, 15)),
    ("15 March 2025", date(2025, 3, 15)), ("2025/03/15", date(2025, 3, 15)),
    ("45731", date(2025, 3, 15)), ("45731.0", date(2025, 3, 15)),
    ("2025-02-30", None), ("31/13/2025", None), ("TBD", None), ("2025-13-05", None),
    ("00/00/0000", None), ("12345", None), ("15-Foo-2025", None), ("", None),
])
def test_parse_date(raw: str, expected: date | None) -> None:
    assert parse_date(raw) == expected


@given(st.dates(min_value=date(1960, 1, 1), max_value=date(2100, 12, 31)))
def test_date_round_trips(d: date) -> None:
    assert parse_date(d.isoformat()) == d
    assert parse_date(d.strftime("%d/%m/%Y")) == d
    assert parse_date(str((d - date(1899, 12, 30)).days)) == d


@pytest.mark.parametrize(("raw", "value", "ok", "ccy"), [
    ("1,234.50", Decimal("1234.50"), True, False), ("(500.00)", Decimal("-500.00"), True, False),
    ("750.00-", Decimal("-750.00"), True, False), ("-12", Decimal("-12"), True, False),
    ("+3.5", Decimal("3.5"), True, False), ("AED 500", Decimal("500"), True, True),
    ("500.00 AED", Decimal("500.00"), True, True), ("\u22125", Decimal("-5"), True, False),
    (".5", Decimal(".5"), True, False), ("", None, True, False),
    ("abc", None, False, False), ("1.00456E+14", None, False, False), ("1.2.3", None, False, False),
])
def test_parse_amount(raw: str, value: Decimal | None, ok: bool, ccy: bool) -> None:
    r = parse_amount(raw)
    assert (r.value, r.ok, r.currency_text) == (value, ok, ccy)


@given(st.decimals(min_value=Decimal("-1e12"), max_value=Decimal("1e12"), places=2,
                   allow_nan=False, allow_infinity=False))
def test_amount_formats_round_trip(v: Decimal) -> None:
    plain = f"{abs(v):,.2f}"
    neg = v < 0
    assert parse_amount(f"({plain})" if neg else plain).value == v
    assert parse_amount(f"{plain}-" if neg else plain).value == v


def test_mapping_synonyms_and_override() -> None:
    headers = ["\ufeffJournal No", "GL Date", "Account", "Dr", "Cr", "Description", "Line ID"]
    m = suggest_mapping(headers)
    assert m == {"voucher_no": "\ufeffJournal No", "posting_date": "GL Date",
                 "account_code": "Account", "debit": "Dr", "credit": "Cr",
                 "narration": "Description", "line_id": "Line ID"}
    m2 = suggest_mapping(headers, {"narration": "", "posting_time": "GL Date"})
    assert "narration" not in m2 and m2["posting_time"] == "GL Date"
    with pytest.raises(ValueError):
        suggest_mapping(headers, {"nonsense": "x"})
    assert norm_header(" Posting-Date ") == "postingdate"


def test_missing_columns() -> None:
    assert missing_columns({}) == ["line_id", "posting_date", "voucher_no", "account_code",
                                   "debit/credit (or amount)"]
    assert missing_columns({"account_code": "a", "closing_balance": "b"}, "TB") == []


def _write(tmp: Path, name: str, rows: list[list[str]]) -> Path:
    p = tmp / name
    p.write_bytes(to_csv_bytes(rows))
    return p


def test_signed_amount_column_and_override(tmp_path: Path) -> None:
    src = _write(tmp_path, "gl.csv", [
        ["Ref", "Date", "Voucher", "GL", "Value", "Junk"],
        ["1", "01/02/2025", "JV-1", "6100", "100.00", "x"],
        ["2", "01/02/2025", "JV-1", "2010", "(100.00)", "x"],
        ["", "", "", "", "", ""],
    ])
    res = parse_to_parquet(src, tmp_path / "o.parquet",
                           override={"line_id": "Ref", "account_code": "GL"})
    assert res.missing_columns == [] and res.unmapped_headers == ["Junk"]
    rows = list(read_parquet_rows(tmp_path / "o.parquet"))
    assert [(r["debit"], r["credit"]) for r in rows] == [
        (Decimal("100"), Decimal("0")), (Decimal("0"), Decimal("100"))]
    assert rows[0]["posting_date"] == date(2025, 2, 1)
    assert validate_parquet(tmp_path / "o.parquet").issues == []


def test_xlsx_import(tmp_path: Path) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.append(["line_id", "posting_date", "voucher_no", "account_code", "debit", "credit"])
    ws.append(["X1", date(2025, 3, 15), "JV-7", 6100, 250.5, 0])
    ws.append(["X2", 45731, "JV-7", 2010, 0, 250.5])
    ws.append(["X3", None, "JV-8", 2010, 0, 0])
    p = tmp_path / "gl.xlsx"
    wb.save(p)
    assert read_headers(p)[0] == "line_id"
    res = parse_to_parquet(p, tmp_path / "x.parquet", chunk_rows=2)
    rows = list(read_parquet_rows(tmp_path / "x.parquet"))
    assert res.rows == 3 and res.chunks == 2
    assert rows[0]["posting_date"] == rows[1]["posting_date"] == date(2025, 3, 15)
    assert rows[0]["account_code"] == "6100"
    codes = [i.code for i in validate_parquet(tmp_path / "x.parquet").issues]
    assert codes == ["missing_mandatory_field"]


def test_empty_file(tmp_path: Path) -> None:
    p = tmp_path / "e.csv"
    p.write_text("")
    res = parse_to_parquet(p, tmp_path / "e.parquet")
    assert res.rows == 0 and "line_id" in res.missing_columns
    rep = validate_parquet(tmp_path / "e.parquet", missing_cols=res.missing_columns)
    assert rep.blocked and {i.code for i in rep.issues} == {"missing_mandatory_column"}


def test_copy_stream_limit(tmp_path: Path) -> None:
    size, digest = copy_stream(io.BytesIO(b"abc"), tmp_path / "a", 10)
    assert size == 3 and digest.startswith("ba7816bf")
    with pytest.raises(ValueError, match="larger"):
        copy_stream(io.BytesIO(b"x" * 20), tmp_path / "b", 10, chunk=4)
    assert not (tmp_path / "b").exists()


def test_profile_dates() -> None:
    assert (date(2025, 3, 15) - timedelta(days=45731)) == date(1899, 12, 30)
