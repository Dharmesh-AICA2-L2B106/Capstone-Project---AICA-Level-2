from app.convert.pdf_inspector import classify_page, inspect_pdf


def test_text_pdf(pdfs):
    info = inspect_pdf(pdfs["simple"])
    assert info.ok and info.page_count == 1 and info.doc_type == "Text" and not info.needs_ocr


def test_multipage(pdfs):
    info = inspect_pdf(pdfs["multipage"])
    assert info.ok and info.page_count >= 3


def test_scanned_pdf_detected(pdfs):
    info = inspect_pdf(pdfs["scanned"])
    assert info.ok and info.doc_type == "Scanned" and info.needs_ocr


def test_mixed_pdf_per_page(pdfs):
    info = inspect_pdf(pdfs["mixed"])
    assert info.page_kinds == ["text", "scanned"]
    assert info.doc_type == "Mixed"


def test_password_protected(pdfs):
    info = inspect_pdf(pdfs["encrypted"])
    assert not info.ok and info.needs_password and info.error.kind == "password"
    wrong = inspect_pdf(pdfs["encrypted"], "wrong")
    assert wrong.error.kind == "wrong_password"
    right = inspect_pdf(pdfs["encrypted"], "secret123")
    assert right.ok and right.page_count == 1


def test_corrupt_and_invalid(pdfs, tmp_path):
    assert inspect_pdf(pdfs["corrupt"]).error.kind == "corrupt"
    assert inspect_pdf(pdfs["not_pdf"]).error.kind == "not_pdf"
    empty = tmp_path / "empty.pdf"
    empty.write_bytes(b"")
    assert inspect_pdf(empty).error.kind == "empty"
    assert inspect_pdf(tmp_path / "missing.pdf").error.kind == "missing"


def test_classify_page():
    assert classify_page(500, 0.0) == "text"
    assert classify_page(500, 0.9) == "mixed"
    assert classify_page(0, 0.95) == "scanned"
    assert classify_page(0, 0.0) == "blank"
