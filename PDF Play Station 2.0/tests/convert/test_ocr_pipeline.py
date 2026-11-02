"""OCR integration tests.

Tesseract itself is an external program. These tests replace it with a fake
engine that returns pre-defined word boxes, so they verify everything around
OCR (page routing, coordinate conversion, table reconstruction, labelling,
warnings) - NOT the recognition accuracy of Tesseract. Real OCR is covered by
test_pdf_to_word.test_scanned_pdf_with_ocr, which runs only when Tesseract
is installed.
"""

from docx import Document
from openpyxl import load_workbook

from app.convert.batch import BatchProcessor
from app.convert.ocr_engine import OcrEngine, OcrStatus, OcrWord, _candidate_paths


class FakeOcr(OcrEngine):
    def __init__(self, words, available=True):
        super().__init__()
        self.words = words
        self.available = available
        self.calls = 0

    def detect(self, refresh=False):
        if self.available:
            return OcrStatus(True, "fake.exe", "5.0", ["eng", "hin"], "Fake OCR")
        return OcrStatus(False, message="not installed")

    def recognise(self, image, lang, timeout=180):
        self.calls += 1
        return list(self.words)


def _table_words(dpi=300):
    """A 3-column statement laid out at 300 dpi pixel coordinates."""
    words = []
    rows = [["Date", "Particulars", "Amount"],
            ["01/04/2024", "Opening", "1,000.00"],
            ["02/04/2024", "Fees", "(250.50)"],
            ["03/04/2024", "Refund", "75.25"]]
    xs = [200, 700, 1500]
    for r, row in enumerate(rows):
        top = 400 + r * 70
        for c, text in enumerate(row):
            words.append(OcrWord(text, xs[c], top, 30 * len(text), 40, 91.0, (1, 1, r + 1)))
    para_top = 900
    for i, w in enumerate("This statement was scanned for testing".split()):
        words.append(OcrWord(w, 200 + i * 190, para_top, 160, 40, 88.0, (2, 1, 1)))
    return words


def test_scanned_page_routed_to_ocr(pdfs, settings):
    ocr = FakeOcr(_table_words())
    res = BatchProcessor([pdfs["scanned"]], settings, ocr).run().results[0]
    assert ocr.calls == 1 and res.ocr_pages == 1
    wb = load_workbook([p for p in res.outputs if p.suffix == ".xlsx"][0])
    rows = [[c.value for c in r] for r in wb["Table_001"].iter_rows()]
    assert rows[0] == ["Source Page", "Date", "Particulars", "Amount"]
    assert rows[2][2:] == ["Fees", -250.5]
    notes = [[c.value for c in r] for r in wb["Conversion_Notes"].iter_rows()]
    assert any(r[3] == "OCR (verify)" for r in notes if r and len(r) > 3)
    text_rows = [[c.value for c in r] for r in wb["Extracted_Text"].iter_rows()]
    assert any(r[4] == "OCR" and "scanned for testing" in (r[3] or "") for r in text_rows[1:])
    doc = Document(str([p for p in res.outputs if p.suffix == ".docx"][0]))
    joined = "\n".join(p.text for p in doc.paragraphs)
    assert "text recognised by OCR" in joined and "Table reconstructed from OCR" in joined
    assert len(doc.tables) == 1


def test_text_pages_are_not_ocrd_in_auto_mode(pdfs, settings):
    ocr = FakeOcr(_table_words())
    BatchProcessor([pdfs["mixed"]], settings, ocr).run()
    assert ocr.calls == 1          # only the scanned second page


def test_always_mode_ocrs_every_page(pdfs, settings):
    ocr = FakeOcr(_table_words())
    settings.ocr_mode = "always"
    BatchProcessor([pdfs["mixed"]], settings, ocr).run()
    assert ocr.calls == 2


def test_ocr_off_flags_scanned_pages(pdfs, settings):
    ocr = FakeOcr(_table_words())
    settings.ocr_mode = "off"
    res = BatchProcessor([pdfs["scanned"]], settings, ocr).run().results[0]
    assert ocr.calls == 0 and res.status == "warning"
    assert any("OCR is turned off" in w for w in res.warnings)


def test_low_confidence_and_empty_ocr_are_flagged(pdfs, settings):
    words = [OcrWord("blurry", 200, 400, 150, 40, 35.0, (1, 1, 1))]
    res = BatchProcessor([pdfs["scanned"]], settings, FakeOcr(words)).run().results[0]
    assert any("confidence is low" in w for w in res.warnings)
    res = BatchProcessor([pdfs["scanned"]], settings, FakeOcr([])).run().results[0]
    assert any("did not recognise any text" in w for w in res.warnings)


def test_missing_language_detected():
    ocr = FakeOcr([])
    assert ocr.missing_languages("eng+hin") == []
    assert ocr.missing_languages("eng+mar") == ["mar"]


def test_configured_tesseract_path_checked_first(tmp_path):
    exe = tmp_path / "tesseract.exe"
    assert _candidate_paths(str(exe))[0] == exe
    assert _candidate_paths(str(tmp_path))[0] == exe


def test_missing_tesseract_reports_clear_message(tmp_path, monkeypatch):
    monkeypatch.setattr("app.convert.ocr_engine._candidate_paths", lambda configured: [tmp_path / "nope.exe"])
    status = OcrEngine().detect(refresh=True)
    assert not status.available and "Tesseract" in status.message and "install" in status.message.lower()
