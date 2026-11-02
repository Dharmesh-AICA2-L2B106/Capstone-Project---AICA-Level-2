"""Secure Redaction: detection, true removal, verification (dummy data only)."""

import io

import pymupdf
import pytest

from app import runners
from app.services import redaction as rd
from app.services.common import UserError
from helpers import requires_tesseract

ALL = rd.DetectionSettings(rd.CATEGORIES)


def cats(text, st=ALL):
    return [(c, text[s:e], conf) for c, s, e, conf, _n in rd.detect_line(text, st)]


# ------------------------------------------------------------------ detection

@pytest.mark.parametrize("line,expected", [
    ("PAN: ABCPK1234Q", ("PAN", "ABCPK1234Q", "High")),
    ("GSTIN 27AAPFU0939F1ZV", ("GSTIN", "27AAPFU0939F1ZV", "High")),
    ("TAN: MUMA12345B", ("TAN", "MUMA12345B", "High")),
    ("CIN U72200MH2009PTC123456", ("CIN", "U72200MH2009PTC123456", "High")),
    ("DIN: 01234567", ("DIN", "01234567", "High")),
    ("IFSC HDFC0001234", ("IFSC", "HDFC0001234", "High")),
    ("Passport No. K1234567", ("Passport", "K1234567", "High")),
    ("Voter ID ABC1234567", ("Voter ID", "ABC1234567", "High")),
    ("Date of birth: 12/03/1985", ("Dates of birth", "12/03/1985", "High")),
    ("DOB 5 March 1990", ("Dates of birth", "5 March 1990", "High")),
    ("Mobile +91 98765 43210", ("Mobile numbers", "+91 98765 43210", "High")),
    ("mail: a.b@example.com", ("E-mail addresses", "a.b@example.com", "High")),
    ("Savings A/c No. 50100123456789", ("Bank account numbers", "50100123456789", "High")),
])
def test_each_category(line, expected):
    assert expected in cats(line)


def test_aadhaar_checksum():
    first11 = "23456789012"
    good = first11 + rd.AadhaarValidator.check_digit(first11)
    bad = first11 + str((int(good[-1]) + 1) % 10)
    assert ("Aadhaar", f"{good[:4]} {good[4:8]} {good[8:]}", "High") in cats(f"UID {good[:4]} {good[4:8]} {good[8:]}")
    assert not [c for c in cats(f"UID {bad}") if c[0] == "Aadhaar"]


def test_gstin_check_character():
    assert rd.gstin_check_char("27AAPFU0939F1Z") == "V"
    assert rd.gstin_valid("27AAPFU0939F1ZV") and not rd.gstin_valid("27AAPFU0939F1ZW")
    assert ("GSTIN", "27AAPFU0939F1ZW", "Medium") in cats("GSTIN 27AAPFU0939F1ZW")


def test_look_alikes_are_not_flagged_or_low():
    assert not cats("Invoice 12345678 dated")                      # 8 digits without 'DIN'
    assert not cats("Order date 12/03/2024")                        # a date without a birth keyword
    assert ("Passport", "K1234567", "Low") in cats("Ref K1234567")  # format only -> unticked by default
    assert not [c for c in cats("Amount 50100123456789") if c[0] == "Bank account numbers"]
    pan_inside_gstin = cats("27AAPFU0939F1ZV")
    assert [c[0] for c in pan_inside_gstin] == ["GSTIN"]            # the PAN inside a GSTIN is not doubled


def test_find_pattern_terms_and_spacing():
    pat, flags = rd.build_find_pattern(["Ramesh Kumar", "1234 5678"], False, True, True)
    import re
    rx = re.compile(pat, flags)
    assert rx.search("Mr RAMESH  kumar") and rx.search("A/c 12345678") and rx.search("1234-5678")
    with pytest.raises(UserError):
        rd.build_find_pattern([" "], False, True, True)


# ------------------------------------------------------------------ fixtures

LINES = ["Name: Ramesh Kumar", "PAN: ABCPK1234Q keep this", "Mobile +91 98765 43210",
         "Savings A/c No. 50100123456789", "Closing words stay here"]


def text_pdf(path, rotate=0, extra_meta=True):
    doc = pymupdf.open()
    p = doc.new_page()
    for i, t in enumerate(LINES):
        p.insert_text((60, 90 + i * 24), t, fontsize=12)
    p.set_rotation(rotate)
    if extra_meta:
        doc.set_metadata({"author": "Ramesh Kumar", "title": "PAN ABCPK1234Q"})
    doc.save(str(path))
    return path


def scanned_pdf(path):
    src = pymupdf.open()
    p = src.new_page()
    for i, t in enumerate(LINES):
        p.insert_text((60, 90 + i * 30), t, fontsize=16)
    pix = p.get_pixmap(dpi=200)
    doc = pymupdf.open()
    sp = doc.new_page(width=p.rect.width, height=p.rect.height)
    sp.insert_image(sp.rect, stream=pix.tobytes("png"))
    doc.save(str(path))
    return path


def status_of(checks, name):
    return next(s for s, c, _d in checks if c == name)


# ------------------------------------------------------------------ redaction

def test_engine_self_test():
    assert rd.engine_ok()


def test_scan_apply_verify_text_pdf(tmp_path, job):
    src = text_pdf(tmp_path / "client.pdf")
    before = src.read_bytes()
    found = rd.scan(job, src, "", ["PAN", "Mobile numbers", "Bank account numbers"])
    vals = {r["text"] for r in found["results"]}
    assert vals == {"ABCPK1234Q", "+91 98765 43210", "50100123456789"}
    regions = {0: [r["rect"] for r in found["results"]]}
    out = tmp_path / "client_redacted.pdf"
    res = rd.apply(job, src, "", regions, out, terms=sorted(vals) + ["Ramesh Kumar"])
    assert not res["failed"], res["checks"]
    with pymupdf.open(str(out)) as d:
        text = d[0].get_text()
        words = {w[4]: w[0] for w in d[0].get_text("words")}
        assert "ABCPK1234Q" not in text and "50100123456789" not in text and "98765" not in text
        assert "keep" in words and "stay" in text                      # neighbours remain searchable
        assert not d.metadata.get("author")
    with pymupdf.open(str(src)) as d:
        orig = {w[4]: w[0] for w in d[0].get_text("words")}
    assert abs(words["keep"] - orig["keep"]) < 0.3                     # text after the PAN did not move
    assert src.read_bytes() == before                                   # original untouched
    checks = res["checks"]
    for name in ("Text inside redacted regions", "Redacted areas blacked out", "Metadata and bookmarks",
                 "Incremental revisions"):
        assert status_of(checks, name) == "PASS", name
    # the name was not marked -> reported as still present elsewhere
    assert status_of(checks, "Redacted values elsewhere in the text") == "WARN"


def test_rotated_page_redaction(tmp_path, job):
    src = text_pdf(tmp_path / "rot.pdf", rotate=90)
    found = rd.find(job, src, "", ["ABCPK1234Q"])
    assert len(found["results"]) == 1
    out = tmp_path / "rot_red.pdf"
    res = rd.apply(job, src, "", {0: [found["results"][0]["rect"]]}, out, terms=["ABCPK1234Q"])
    assert not res["failed"]
    with pymupdf.open(str(out)) as d:
        assert d[0].rotation == 90 and "ABCPK1234Q" not in d[0].get_text() and "keep" in d[0].get_text()


def test_annotations_and_links_in_region_removed(tmp_path, job):
    src = text_pdf(tmp_path / "a.pdf")
    with pymupdf.open(str(src)) as d:
        r = d[0].search_for("ABCPK1234Q")[0]
        d[0].add_text_annot(r.tl, "PAN ABCPK1234Q")
        d[0].insert_link({"kind": pymupdf.LINK_URI, "from": r, "uri": "https://example.com"})
        d.save(str(tmp_path / "b.pdf"))
    out = tmp_path / "b_red.pdf"
    res = rd.apply(job, tmp_path / "b.pdf", "", {0: [tuple(r)]}, out, terms=["ABCPK1234Q"])
    assert status_of(res["checks"], "Annotations / form fields in regions") == "PASS"
    with pymupdf.open(str(out)) as d:
        assert not list(d[0].annots()) and not d[0].get_links()


def test_verification_catches_unredacted_file(tmp_path, job):
    src = text_pdf(tmp_path / "c.pdf")
    with pymupdf.open(str(src)) as d:
        rect = tuple(d[0].search_for("ABCPK1234Q")[0])
    checks = rd.verify_output(job, src, 1, {0: [rect]}, ["ABCPK1234Q"], sanitised=True)
    assert status_of(checks, "Text inside redacted regions") == "FAIL"
    assert status_of(checks, "Redacted areas blacked out") == "FAIL"
    assert status_of(checks, "Metadata and bookmarks") == "FAIL"


def test_output_must_be_new_file_and_password_source(tmp_path, job):
    src = text_pdf(tmp_path / "d.pdf")
    with pytest.raises(UserError):
        rd.apply(job, src, "", {0: [(50, 50, 100, 100)]}, src)
    with pymupdf.open(str(src)) as d:
        d.save(str(tmp_path / "locked.pdf"), encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="pw", owner_pw="ow")
    out = tmp_path / "locked_red.pdf"
    res = rd.apply(job, tmp_path / "locked.pdf", "pw", {0: [(50, 100, 200, 120)]}, out)
    assert res["was_encrypted"]
    with pymupdf.open(str(out)) as d:
        assert not d.needs_pass


def test_flatten_all(tmp_path, job):
    src = text_pdf(tmp_path / "f.pdf")
    out = tmp_path / "f_red.pdf"
    res = rd.apply(job, src, "", {0: [(50, 100, 200, 120)]}, out, flatten_all=True)
    assert res["flattened"] and not res["failed"]
    with pymupdf.open(str(out)) as d:
        assert not d[0].get_text().strip()


def test_inspect_and_verify_runner(tmp_path, job):
    src = text_pdf(tmp_path / "e.pdf")
    res = rd.inspect(job, src, "", ["ABCPK1234Q", "Not There 999"])
    statuses = {c: s for s, c, _d in res["checks"]}
    assert statuses[f"Term {rd.mask_value('ABCPK1234Q')}"] == "FOUND"
    r = runners.verify(job, [str(src)], {"Values that must not appear": ["ABCPK1234Q"],
                                         "Read scanned pages with OCR": False, "OCR language": "English"}, "", {})
    assert "need attention" in r["message"] and r["warnings"]
    assert any(line.startswith("FOUND") for line in r["details"])


# ------------------------------------------------------------------ scanned pages (OCR)

@requires_tesseract
def test_scanned_pdf_detect_redact_verify(tmp_path, job):
    src = scanned_pdf(tmp_path / "scan.pdf")
    off = rd.scan(job, src, "", ["PAN"], ocr_mode="Off")
    assert not off["results"] and off["no_text"] == [1]
    found = rd.scan(job, src, "", ["PAN", "Bank account numbers"], ocr_lang="eng")
    assert found["ocr_pages"] == [1] and "0" in found["ocr_cache"]
    assert {r["text"] for r in found["results"]} >= {"ABCPK1234Q", "50100123456789"}
    assert all(r["ocr"] for r in found["results"])
    again = rd.find(job, src, "", ["Ramesh Kumar"], ocr_cache=found["ocr_cache"])   # cached OCR re-used
    assert len(again["results"]) == 1
    terms = [r["text"] for r in found["results"]] + ["Ramesh Kumar"]
    regions = {0: [r["rect"] for r in found["results"] + again["results"]]}
    out = tmp_path / "scan_red.pdf"
    res = rd.apply(job, src, "", regions, out, terms=terms, ocr_lang="eng")
    assert not res["failed"], res["checks"]
    assert status_of(res["checks"], "Redacted areas blacked out") == "PASS"
    assert status_of(res["checks"], "Values readable on scanned pages (OCR)") == "PASS"
    # independent check: OCR of the saved page no longer reads the values
    with pymupdf.open(str(out)) as d:
        text = rd.normalise(" ".join(t for t, _b in rd.ocr_lines(d[0], "eng")))
    assert "abcpk1234q" not in text and "50100123456789" not in text and "rameshkumar" not in text
    assert "closingwords" in text                                       # the rest is still readable


@requires_tesseract
def test_inspect_reads_scanned_pages(tmp_path, job):
    src = scanned_pdf(tmp_path / "scan.pdf")
    res = rd.inspect(job, src, "", ["ABCPK1234Q"], ocr_lang="eng")
    found = [d for s, c, d in res["checks"] if s == "FOUND"]
    assert found and "OCR" in found[0]
