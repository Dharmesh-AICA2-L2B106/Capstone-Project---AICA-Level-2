"""D56: mapping overrides are normalised and checked against the file before a parse job."""

from __future__ import annotations

from typing import Any

import pytest

from app.services.importer import (
    ALLOWED_FIELDS,
    MappingError,
    canonical_field,
    normalise_override,
    suggest_mapping,
)

HEADERS = ["\ufeffPosting Date", "Voucher No", "Account", "Dr", "Cr", "Narration", "Line ID"]


def _err(override: Any, headers: list[str] = HEADERS) -> str:
    with pytest.raises(MappingError) as ei:
        normalise_override(override, headers)
    assert str(ei.value) == ei.value.message
    return ei.value.message


def test_canonical_field() -> None:
    assert canonical_field("posting_date") == "posting_date"
    assert canonical_field("Posting Date") == "posting_date"
    assert canonical_field("date") == "posting_date"
    assert canonical_field("Dr") == "debit"
    assert canonical_field("Voucher-No") == "voucher_no"
    assert canonical_field("zzz") is None
    assert "posting_date" in ALLOWED_FIELDS and "closing_balance" in ALLOWED_FIELDS


def test_canonical_keys_pass_through() -> None:
    assert normalise_override(None, HEADERS) is None
    assert normalise_override({}, HEADERS) == {}
    out = normalise_override({"posting_date": "\ufeffPosting Date", "narration": ""}, HEADERS)
    assert out == {"posting_date": "\ufeffPosting Date", "narration": ""}


def test_label_and_synonym_keys() -> None:
    out = normalise_override({"Posting Date": "Posting Date", "Voucher No": "Voucher No",
                              "date ": "Posting Date", "Dr": "Dr", "CR": "Cr",
                              "account": "Account"}, HEADERS)
    # header values are resolved to the exact header (here with its BOM)
    assert out == {"posting_date": "\ufeffPosting Date", "voucher_no": "Voucher No",
                   "debit": "Dr", "credit": "Cr", "account_code": "Account"}


def test_header_value_matched_loosely_when_unique() -> None:
    out = normalise_override({"posting_date": "posting date", "voucher_no": "VOUCHER_NO"},
                             HEADERS)
    assert out == {"posting_date": "\ufeffPosting Date", "voucher_no": "Voucher No"}
    two = ["Posting Date", "posting-date"]
    assert "not in the file" in _err({"posting_date": "postingdate"}, two)


def test_reversed_direction() -> None:
    out = normalise_override({"Posting Date": "posting_date", "Account": "account_code",
                              "Line ID": "line_id", "Dr": "debit"}, HEADERS)
    assert out == {"posting_date": "\ufeffPosting Date", "account_code": "Account",
                   "line_id": "Line ID", "debit": "Dr"}
    odd = ["Fecha", "Importe"]  # headers that are no synonym at all
    assert normalise_override({"Fecha": "posting_date", "Importe": "Amount"}, odd) == {
        "posting_date": "Fecha", "amount": "Importe"}


def test_unknown_keys_listed_with_allowed_fields() -> None:
    msg = _err({"zzz": "Dr", "Fecha": "Dr"})
    assert msg.startswith("Mapping problem: Unknown fields 'zzz', 'Fecha' in the mapping.")
    assert "Allowed fields: line_id, entry_date, posting_date," in msg
    one = _err({"zzz": "Dr"})
    assert "Unknown field 'zzz' in the mapping." in one


def test_header_not_in_file() -> None:
    msg = _err({"posting_date": "Txn Date"})
    assert ("Column 'Txn Date' (mapped to posting_date) is not in the file. Columns in the "
            "file: Posting Date, Voucher No, Account, Dr, Cr, Narration, Line ID.") in msg
    many = [f"c{i}" for i in range(45)]
    assert "(+5 more)." in _err({"debit": "nope"}, many)


def test_values_must_be_text() -> None:
    assert "The value for 'debit' must be a column header (text)" in _err({"debit": 5})
    assert "got a number" in _err({"debit": 5.5})
    assert "got true/false" in _err({"debit": True})
    assert "got a list" in _err({"debit": ["Dr"]})
    assert "got an object" in _err({"debit": {"h": "Dr"}})
    assert normalise_override({"debit": None}, HEADERS) == {"debit": ""}  # null = unmap
    assert "must be a JSON object" in _err(["posting_date"])
    assert "must be a JSON object" in _err("posting_date=Posting Date")


def test_field_mapped_twice() -> None:
    msg = _err({"debit": "Dr", "Dr Amount": "Cr"})
    assert "debit is mapped twice ('debit' and 'Dr Amount')" in msg
    assert normalise_override({"debit": "Dr", "Dr": "Dr"}, HEADERS) == {"debit": "Dr"}


def test_problems_reported_together() -> None:
    msg = _err({"zzz": "x", "credit": 0, "debit": "Nope"})
    assert "Unknown field 'zzz'" in msg and "'credit'" in msg and "'Nope'" in msg


def test_suggest_mapping_still_refuses_non_canonical_keys() -> None:
    with pytest.raises(MappingError, match="Unknown field 'Posting Date'"):
        suggest_mapping(HEADERS, {"Posting Date": "x"})
    with pytest.raises(ValueError):  # MappingError stays a ValueError for older callers
        suggest_mapping(HEADERS, {"nonsense": "x"})
