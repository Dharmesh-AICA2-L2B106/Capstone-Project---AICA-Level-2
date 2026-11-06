"""Local OCR through the Tesseract program (Apache-2.0).

Tesseract runs as a local process on a temporary image; nothing leaves the
computer. It is looked for in a 'tesseract' folder next to the application, on
PATH, then in the standard Windows install folders."""

from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Optional

log = logging.getLogger("pps.ocr")

ROOT = Path(__file__).resolve().parents[2]
LANGUAGE_CHOICES = {"English": "eng", "English + Hindi": "eng+hin", "English + Marathi": "eng+mar",
                    "English + Hindi + Marathi": "eng+hin+mar"}
INSTALL_HINT = ("Install Tesseract OCR for Windows (UB Mannheim build) with the English, Hindi and "
                "Marathi language data, then restart PDF Play Station.")


class OcrError(Exception):
    pass


@dataclass
class OcrStatus:
    available: bool
    path: Optional[str] = None
    version: str = ""
    languages: list[str] = field(default_factory=list)
    message: str = ""


def _candidates() -> list[Path]:
    out = [ROOT / "tesseract" / "tesseract.exe"]
    found = shutil.which("tesseract")
    if found:
        out.append(Path(found))
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"),
                 os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs")):
        if base:
            out.append(Path(base) / "Tesseract-OCR" / "tesseract.exe")
    return out


@lru_cache(maxsize=1)
def status() -> OcrStatus:
    try:
        import pytesseract
    except ImportError:
        return OcrStatus(False, message="The pytesseract component is not installed.")
    for cand in _candidates():
        if not cand.is_file():
            continue
        pytesseract.pytesseract.tesseract_cmd = str(cand)
        if cand.parent == ROOT / "tesseract" and (cand.parent / "tessdata").is_dir():
            os.environ["TESSDATA_PREFIX"] = str(cand.parent / "tessdata")
        try:
            version = str(pytesseract.get_tesseract_version())
            # language files in tessdata sub-folders (backups) are listed as "folder/lang"; ignore them
            langs = sorted(l for l in pytesseract.get_languages(config="") if "/" not in l and "\\" not in l)
        except Exception as exc:
            log.warning("Tesseract at %s could not be started: %s", cand, exc)
            continue
        log.info("Tesseract %s at %s (%s)", version, cand, ", ".join(langs))
        return OcrStatus(True, str(cand), version, langs, f"Tesseract {version}")
    return OcrStatus(False, message="Tesseract OCR was not found on this computer. " + INSTALL_HINT)


def require(lang: str = "eng", osd: bool = False) -> None:
    st = status()
    if not st.available:
        raise OcrError(st.message)
    wanted = [l for l in (lang or "eng").split("+") if l] + (["osd"] if osd else [])
    missing = [l for l in wanted if l not in st.languages]
    if missing:
        raise OcrError(f"OCR language data missing: {', '.join(missing)}. " + INSTALL_HINT)


def image_to_text(image, lang: str = "eng", psm: int = 3, timeout: int = 180) -> str:
    require(lang)
    import pytesseract
    try:
        return pytesseract.image_to_string(image, lang=lang, config=f"--psm {psm}", timeout=timeout)
    except RuntimeError as exc:
        raise OcrError(f"OCR stopped: {exc}") from exc
    except pytesseract.TesseractError as exc:
        raise OcrError(f"OCR failed: {exc.message or exc}") from exc


def orientation(image, dpi: int = 150, timeout: int = 60) -> tuple[Optional[int], float]:
    """Clockwise turn (0/90/180/270) that makes the image upright, and Tesseract's
    confidence. (None, 0) when there is too little text to decide.
    (Checked: a page displayed 90° clockwise returns 270.)"""
    require("eng", osd=True)
    import pytesseract
    try:
        info = pytesseract.image_to_osd(image, config=f"--psm 0 --dpi {dpi}", timeout=timeout,
                                        output_type=pytesseract.Output.DICT)
    except (RuntimeError, pytesseract.TesseractError) as exc:
        log.info("Orientation check could not decide: %s", exc)
        return None, 0.0
    return int(info.get("rotate", 0)) % 360, float(info.get("orientation_conf", 0.0))
