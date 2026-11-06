"""Fixtures for the conversion engine tests (carried over from PDF Converter Pro)."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pdf_factory  # noqa: E402
from app.convert.ocr_engine import OcrStatus  # noqa: E402
from app.convert.settings import ConversionSettings  # noqa: E402
from convert_helpers import NoOcr  # noqa: E402


@pytest.fixture(scope="session")
def pdfs(tmp_path_factory):
    """All synthetic PDFs, generated once per test session."""
    d = tmp_path_factory.mktemp("pdfs")
    return {
        "simple": pdf_factory.simple_text_pdf(d / "simple.pdf"),
        "table": pdf_factory.table_pdf(d / "table.pdf"),
        "multipage": pdf_factory.multipage_table_pdf(d / "multipage.pdf"),
        "borderless": pdf_factory.borderless_table_pdf(d / "borderless.pdf"),
        "scanned": pdf_factory.scanned_pdf(d / "scanned.pdf", d),
        "mixed": pdf_factory.mixed_pdf(d / "mixed.pdf", d),
        "landscape": pdf_factory.landscape_pdf(d / "landscape.pdf"),
        "encrypted": pdf_factory.encrypted_pdf(d / "encrypted.pdf"),
        "corrupt": pdf_factory.corrupt_pdf(d / "corrupt.pdf"),
        "not_pdf": pdf_factory.not_a_pdf(d / "not_pdf.pdf"),
        "twocol": pdf_factory.two_column_pdf(d / "twocol.pdf"),
    }


@pytest.fixture
def no_ocr():
    return NoOcr()


@pytest.fixture
def settings(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    return ConversionSettings(output_format="both", output_folder=out, conflict_policy="increment")
