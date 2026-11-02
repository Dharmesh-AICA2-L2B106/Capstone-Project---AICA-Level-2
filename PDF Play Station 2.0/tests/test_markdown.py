import io

import pymupdf
from PIL import Image

from app.services import markdown_pdf as mdp
from helpers import requires_tesseract

MD = """# Annual Report

Some **bold** text, *italic* text and `code`.

- First point
- Second point

| Year | Revenue |
| --- | --- |
| 2025 | 1,00,000 |

<script>alert('x')</script>

![missing](nothere.png) ![remote](https://example.com/a.png)
"""


def test_markdown_to_pdf(tmp_path, job):
    src = tmp_path / "notes.md"
    src.write_text(MD, encoding="utf-8")
    out = tmp_path / "notes.pdf"
    r = mdp.markdown_to_pdf(job, src, out, title="Board Notes", header_text="Confidential",
                            footer_text="K&P")
    with pymupdf.open(str(out)) as d:
        text = d[0].get_text()
    for expected in ("Board Notes", "Annual Report", "First point", "1,00,000", "Confidential", "Page 1 of 1"):
        assert expected in text
    assert "alert" not in text
    joined = " ".join(r.warnings)
    assert "script" in joined and "not found" in joined and "not downloaded" in joined


def test_markdown_hindi_marathi_text(tmp_path, job):
    src = tmp_path / "hi.md"
    src.write_text("# सूचना\n\nखाते का विवरण - मराठी: खातेदाराचे नाव\n", encoding="utf-8")
    out = tmp_path / "hi.pdf"
    mdp.markdown_to_pdf(job, src, out)
    with pymupdf.open(str(out)) as d:
        text = d[0].get_text()
    assert "सूचना" in text and "खातेदाराचे" in text


def test_pdf_to_markdown_structure(tmp_path, job):
    src = tmp_path / "notes.md"
    src.write_text(MD, encoding="utf-8")
    pdf = tmp_path / "notes.pdf"
    mdp.markdown_to_pdf(job, src, pdf)
    out = tmp_path / "back.md"
    mdp.pdf_to_markdown(job, pdf, "", out, [1])
    md = out.read_text(encoding="utf-8")
    assert md.startswith("# Annual Report")
    assert "- First point" in md
    assert "| 2025 | 1,00,000 |" in md
    assert "**bold**" in md


@requires_tesseract
def test_pdf_to_markdown_ocr_scanned(tmp_path, job):
    text_pdf = pymupdf.open()
    p = text_pdf.new_page()
    p.insert_text((72, 100), "Statement of Account", fontsize=20)
    p.insert_text((72, 140), "Opening balance as on 1 April 2025", fontsize=12)
    pix = p.get_pixmap(dpi=200)
    scan = pymupdf.open()
    sp = scan.new_page()
    sp.insert_image(sp.rect, stream=pix.tobytes("png"))
    scan.save(str(tmp_path / "scan.pdf"))
    out = tmp_path / "scan.md"
    r = mdp.pdf_to_markdown(job, tmp_path / "scan.pdf", "", out, [1], ocr_lang="eng")
    md = out.read_text(encoding="utf-8")
    assert "Statement of Account" in md and "Opening balance" in md
    assert any("OCR" in w for w in r.warnings)
    off = tmp_path / "off.md"
    r2 = mdp.pdf_to_markdown(job, tmp_path / "scan.pdf", "", off, [1], ocr_mode="Off")
    assert "Statement" not in off.read_text(encoding="utf-8")
    assert any("No text" in w for w in r2.warnings)
