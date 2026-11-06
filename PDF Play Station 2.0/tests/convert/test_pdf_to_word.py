import pytest
from docx import Document
from docx.shared import Pt

from app.convert.batch import BatchProcessor
from convert_helpers import tesseract_available


def convert(path, settings, ocr):
    settings.output_format = "word"
    res = BatchProcessor([path], settings, ocr).run().results[0]
    assert res.status in ("success", "warning"), res.error
    return res, Document(str(res.outputs[0]))


def texts(doc):
    return [p.text for p in doc.paragraphs if p.text.strip()]


def test_editable_document_structure(pdfs, settings, no_ocr):
    _, doc = convert(pdfs["simple"], settings, no_ocr)
    paras = {p.text: p for p in doc.paragraphs if p.text.strip()}
    assert paras["Annual Compliance Note"].style.name.startswith("Heading")
    assert paras["Introduction"].style.name.startswith("Heading")
    body = next(p for t, p in paras.items() if t.startswith("This synthetic document"))
    # wrapped lines were joined into one paragraph
    assert "line joining can be verified by the automated tests in this project." in body.text
    assert any(r.bold and "bold words" in r.text for r in body.runs)
    assert any(r.italic and "italic words" in r.text for r in body.runs)
    # bullets kept as separate list paragraphs
    bullets = [t for t in paras if t.startswith("•")]
    assert [b.split(None, 1)[1] for b in bullets] == ["First bullet point", "Second bullet point"]
    # hyperlink retained
    assert "https://example.com" in [r.target_ref for r in doc.part.rels.values() if r.is_external]


def test_tables_become_word_tables(pdfs, settings, no_ocr):
    _, doc = convert(pdfs["table"], settings, no_ocr)
    assert len(doc.tables) == 1
    t = doc.tables[0]
    assert [c.text for c in t.rows[0].cells] == ["Particulars", "Account No", "Amount", "Change", "Date"]
    assert t.rows[3].cells[2].text == "(1,200.00)"       # original text preserved exactly in Word
    assert t.rows[1].cells[1].text == "000123"


def test_page_size_and_orientation(pdfs, settings, no_ocr):
    _, doc = convert(pdfs["landscape"], settings, no_ocr)
    sec = doc.sections[0]
    assert sec.page_width > sec.page_height
    assert abs(sec.page_width - Pt(842)) < Pt(2)


def test_two_column_reading_order(pdfs, settings, no_ocr):
    _, doc = convert(pdfs["twocol"], settings, no_ocr)
    joined = "\n".join(texts(doc))
    # the whole left column is read before the right column; columns are not interleaved
    assert joined.index("Left column sentence number 15") < joined.index("Right column line 1 ")
    assert "continues here. Right column" not in joined


@pytest.mark.parametrize("mode", ["layout", "text"])
def test_other_word_modes(pdfs, settings, no_ocr, mode):
    settings.word_mode = mode
    _, doc = convert(pdfs["table"], settings, no_ocr)
    all_text = "\n".join(texts(doc))
    assert len(doc.tables) == 1
    if mode == "layout":
        assert doc.inline_shapes, "page picture expected"
        assert "Editable text (extracted)" in all_text
    else:
        assert "Page 1" in all_text and not doc.inline_shapes


def test_scanned_page_without_ocr_is_flagged_not_dropped(pdfs, settings, no_ocr):
    res, doc = convert(pdfs["scanned"], settings, no_ocr)
    assert res.status == "warning"
    assert any("scanned" in w and "OCR" in w for w in res.warnings)
    assert doc.inline_shapes, "the page image is kept so no content is lost"
    assert any("could not be extracted" in t for t in texts(doc))


def test_mixed_pdf_processes_each_page(pdfs, settings, no_ocr):
    res, doc = convert(pdfs["mixed"], settings, no_ocr)
    assert res.pages_processed == 2
    assert any("real, extractable text" in t for t in texts(doc))
    assert any("Page 2" in w for w in res.warnings)


@pytest.mark.skipif(not tesseract_available(), reason="Tesseract OCR is not installed on this machine")
def test_scanned_pdf_with_ocr(pdfs, settings):
    from app.convert.ocr_engine import OcrEngine
    res, doc = convert(pdfs["scanned"], settings, OcrEngine())
    assert res.ocr_pages == 1
    joined = " ".join(texts(doc))
    assert "INVOICE" in joined.upper() and "4521" in joined
