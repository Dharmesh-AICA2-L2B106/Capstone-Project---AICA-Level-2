"""Conversion engine for Section 2 (PDF to Excel / Word and balance-checked bank
statements).

Copied on 29-10-2026 from PDF Converter Pro 1.0.0 (app\\*.py, engine modules only;
the original tool was not changed). Changes made while copying: this package
header, config.py reduced to the folder lookup used by ocr_engine.py, and the
import path of the tests. Everything else is the proven Converter Pro code.
"""

from .. import APP_NAME, APP_VERSION  # noqa: F401  (written into workbook / document properties)
