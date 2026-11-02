"""Used by run.bat: decides whether components need to be (re)installed.

    python tools\\check_requirements.py check    -> exit 0 if everything is installed
    python tools\\check_requirements.py imports  -> exit 0 if every module imports
    python tools\\check_requirements.py stamp    -> record that requirements.txt was installed

The stamp (a hash of requirements.txt stored inside .venv) means packages are
only reinstalled when requirements.txt changes, not on every launch.
"""

import hashlib
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS = ROOT / "requirements.txt"
STAMP = Path(sys.prefix) / ".pps_requirements.sha256"
MODULES = ["PySide6.QtWidgets", "PySide6.QtSvg", "pymupdf", "pdfplumber", "pypdfium2", "openpyxl",
           "docx", "pytesseract", "PIL", "markdown"]


def digest() -> str:
    return hashlib.sha256(REQUIREMENTS.read_bytes()).hexdigest()


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "check"
    if mode == "stamp":
        STAMP.write_text(digest(), encoding="ascii")
        return 0
    missing = []
    for name in MODULES:
        try:
            importlib.import_module(name)
        except Exception:
            missing.append(name)
    if missing:
        print("       Missing or broken components: " + ", ".join(missing))
        return 1
    if mode == "imports":
        return 0
    if not STAMP.exists() or STAMP.read_text(encoding="ascii").strip() != digest():
        print("       The list of required components has changed.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
