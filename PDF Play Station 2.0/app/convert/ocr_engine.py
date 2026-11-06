"""Local OCR through the Tesseract engine (Apache-2.0).

Tesseract is an external program, not a Python package. It is located in
this order:

1. the path configured by the user (Advanced Settings / config.json),
2. a ``tesseract`` folder bundled next to the application,
3. the system PATH,
4. the default Windows install folders.

No document data ever leaves the computer: Tesseract runs as a local
process on a temporary image.
"""

from __future__ import annotations

import logging
import os
import shutil
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .config import app_root, resource_path

log = logging.getLogger(__name__)

TESSERACT_DOWNLOAD_HINT = (
    "Install Tesseract OCR for Windows (for example the UB Mannheim build from "
    "https://github.com/UB-Mannheim/tesseract/wiki), then restart the application "
    "or set its location under Advanced Settings > Tesseract path."
)


class OcrError(Exception):
    pass


@dataclass
class OcrStatus:
    available: bool
    path: Optional[str] = None
    version: str = ""
    languages: list[str] = field(default_factory=list)
    message: str = ""


@dataclass
class OcrWord:
    text: str
    left: int
    top: int
    width: int
    height: int
    conf: float
    line_key: tuple[int, int, int]


def _candidate_paths(configured: str) -> list[Path]:
    candidates: list[Path] = []
    if configured:
        p = Path(configured)
        candidates.append(p / "tesseract.exe" if p.is_dir() else p)
    candidates += [resource_path("tesseract", "tesseract.exe"), app_root() / "tesseract" / "tesseract.exe"]
    found = shutil.which("tesseract")
    if found:
        candidates.append(Path(found))
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"),
                 os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs")):
        if base:
            candidates.append(Path(base) / "Tesseract-OCR" / "tesseract.exe")
    return candidates


class OcrEngine:
    def __init__(self, configured_path: str = ""):
        self.configured_path = configured_path
        self._status: Optional[OcrStatus] = None
        self._lock = threading.Lock()

    def detect(self, refresh: bool = False) -> OcrStatus:
        with self._lock:
            if self._status is None or refresh:
                self._status = self._detect()
            return self._status

    def _detect(self) -> OcrStatus:
        try:
            import pytesseract
        except ImportError:
            return OcrStatus(False, message="The pytesseract package is not installed.")
        for candidate in _candidate_paths(self.configured_path):
            if not candidate.is_file():
                continue
            pytesseract.pytesseract.tesseract_cmd = str(candidate)
            tessdata = candidate.parent / "tessdata"
            bundled = candidate.parent in (resource_path("tesseract"), app_root() / "tesseract")
            if bundled and tessdata.is_dir():
                os.environ["TESSDATA_PREFIX"] = str(tessdata)
            try:
                version = str(pytesseract.get_tesseract_version())
                # Models in tessdata sub-folders (e.g. backups) are listed as "folder/lang"; ignore them.
                languages = sorted(l for l in pytesseract.get_languages(config="")
                                   if l != "osd" and "/" not in l and "\\" not in l)
            except Exception as exc:  # broken install, missing DLLs, ...
                log.warning("Tesseract at %s could not be started: %s", candidate, exc)
                continue
            if not languages:
                return OcrStatus(False, str(candidate), version, [],
                                 "Tesseract was found but no OCR language data is installed.")
            log.info("Tesseract %s found at %s (languages: %s)", version, candidate, ", ".join(languages))
            return OcrStatus(True, str(candidate), version, languages, f"Tesseract {version}")
        return OcrStatus(False, message="Tesseract OCR was not found on this computer. " + TESSERACT_DOWNLOAD_HINT)

    def missing_languages(self, lang_spec: str) -> list[str]:
        status = self.detect()
        wanted = [l for l in (lang_spec or "eng").split("+") if l]
        return [l for l in wanted if l not in status.languages]

    def read_text(self, image, psm: int = 7, whitelist: str = "", timeout: int = 30) -> str:
        """Plain-text OCR of a small image (e.g. one table cell), optionally digits only."""
        status = self.detect()
        if not status.available:
            raise OcrError(status.message)
        import pytesseract
        config = f"--psm {psm}" + (f" -c tessedit_char_whitelist={whitelist}" if whitelist else "")
        try:
            return pytesseract.image_to_string(image, lang="eng", config=config, timeout=timeout)
        except (RuntimeError, pytesseract.TesseractError) as exc:
            raise OcrError(f"OCR failed: {exc}") from exc

    def recognise(self, image, lang: str, timeout: int = 180, psm: int = 3, whitelist: str = "") -> list[OcrWord]:
        """Run OCR on a PIL image and return recognised words with boxes (pixels)."""
        status = self.detect()
        if not status.available:
            raise OcrError(status.message)
        import pytesseract
        from pytesseract import Output
        config = f"--psm {psm}" + (f" -c tessedit_char_whitelist={whitelist}" if whitelist else "")
        try:
            data = pytesseract.image_to_data(image, lang=lang or "eng", config=config,
                                             timeout=timeout, output_type=Output.DICT)
        except RuntimeError as exc:
            if "timeout" in str(exc).lower():
                raise OcrError(f"OCR took longer than {timeout} seconds and was stopped.") from exc
            raise OcrError(f"OCR failed: {exc}") from exc
        except pytesseract.TesseractError as exc:
            raise OcrError(f"OCR failed: {exc.message or exc}") from exc
        words: list[OcrWord] = []
        for i, text in enumerate(data["text"]):
            text = (text or "").strip()
            try:
                conf = float(data["conf"][i])
            except (TypeError, ValueError):
                conf = -1.0
            if not text or conf < 0:
                continue
            words.append(OcrWord(text, int(data["left"][i]), int(data["top"][i]), int(data["width"][i]),
                                 int(data["height"][i]), conf,
                                 (int(data["block_num"][i]), int(data["par_num"][i]), int(data["line_num"][i]))))
        return words
