"""Helpers for the conversion engine tests."""

from app.convert.ocr_engine import OcrEngine, OcrStatus


class NoOcr(OcrEngine):
    """OCR engine that reports Tesseract as unavailable (deterministic tests)."""

    def detect(self, refresh: bool = False) -> OcrStatus:
        return OcrStatus(False, message="Tesseract OCR was not found (test).")


def tesseract_available() -> bool:
    return OcrEngine().detect().available
