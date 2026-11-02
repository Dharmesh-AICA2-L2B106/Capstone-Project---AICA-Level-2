import pytest

from app.convert.validators import (ValidationError, check_output_folder, pages_for_document, parse_page_range,
                            safe_filename, safe_sheet_name)


def test_page_range_parsing():
    assert parse_page_range("") is None
    assert parse_page_range("1, 3-5, 8-10") == [(1, 1), (3, 5), (8, 10)]
    assert parse_page_range(" 2 - 4 ") == [(2, 4)]


@pytest.mark.parametrize("bad", ["0", "5-3", "a", "1,,2", "1-", "-3", "1-2-3", "1.5"])
def test_invalid_page_ranges(bad):
    with pytest.raises(ValidationError):
        parse_page_range(bad)


def test_page_range_against_document():
    assert pages_for_document(parse_page_range("1, 3-4, 3"), 5) == [1, 3, 4]
    assert pages_for_document(None, 3) == [1, 2, 3]
    with pytest.raises(ValidationError, match="only 5 page"):
        pages_for_document(parse_page_range("4-8"), 5)


def test_sheet_names_are_valid_and_unique():
    used: set[str] = set()
    a = safe_sheet_name("Revenue: Q1/Q2 [draft]*?", used)
    assert not any(ch in a for ch in "[]:*?/\\") and len(a) <= 31
    long_name = "X" * 40
    b = safe_sheet_name(long_name, used)
    c = safe_sheet_name(long_name, used)
    assert len(b) <= 31 and len(c) <= 31 and b.lower() != c.lower()
    assert safe_sheet_name("History", used) != "History"
    assert safe_sheet_name("", used, "Table") == "Table"


def test_safe_filename():
    assert safe_filename('a<b>c:"d"/e|f?g*') == "a_b_c__d__e_f_g_"
    assert safe_filename("CON") == "_CON"
    assert safe_filename("   ") == "Converted"


def test_output_folder_checks(tmp_path):
    check_output_folder(tmp_path)
    with pytest.raises(ValidationError, match="does not exist"):
        check_output_folder(tmp_path / "missing")
    f = tmp_path / "file.txt"
    f.write_text("x")
    with pytest.raises(ValidationError, match="not a folder"):
        check_output_folder(f)
