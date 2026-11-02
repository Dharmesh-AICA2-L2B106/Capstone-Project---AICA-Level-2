import pytest

from app.services.common import (UserError, output_path, page_runs, parse_page_groups, parse_pages,
                                 unique_path)


def test_page_groups_basic():
    assert parse_page_groups("1, 3-5, 8-end", 10) == [[1], [3, 4, 5], [8, 9, 10]]
    assert parse_page_groups("5-3", 6) == [[5, 4, 3]]
    assert parse_page_groups(" 2 – 4 ", 6) == [[2, 3, 4]]          # en dash and spaces


@pytest.mark.parametrize("text", ["0", "11", "-2", "a", "3-x", "1--2"])
def test_page_groups_rejects(text):
    with pytest.raises(UserError):
        parse_page_groups(text, 10)


def test_parse_pages_blank_and_duplicates():
    assert parse_pages("", 3) == [1, 2, 3]
    assert parse_pages("2, 1-3", 3) == [2, 1, 3]
    with pytest.raises(UserError):
        parse_pages("", 3, blank_means_all=False)


def test_page_runs():
    assert page_runs([1, 2, 3, 7, 6, 5, 9]) == [(1, 3), (7, 5), (9, 9)]


def test_unique_path_never_overwrites(tmp_path):
    (tmp_path / "a.pdf").write_bytes(b"x")
    taken = set()
    first = unique_path(tmp_path / "a.pdf", taken)
    second = unique_path(tmp_path / "a.pdf", taken)
    assert first.name == "a (2).pdf" and second.name == "a (3).pdf"


def test_output_path_naming(tmp_path):
    src = tmp_path / "Report.pdf"
    assert output_path(src, "", "_rotated", ".pdf").name == "Report_rotated.pdf"
    out = tmp_path / "out"
    assert output_path(src, str(out), "", ".pdf", name="Merged.pdf") == out / "Merged.pdf"
    assert output_path(src, "", "", ".pdf", name='bad:name?.pdf').name == "bad_name_.pdf"
