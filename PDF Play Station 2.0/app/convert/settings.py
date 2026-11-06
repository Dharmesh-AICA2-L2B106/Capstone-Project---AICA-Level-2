"""Conversion settings chosen by the user for one batch."""

from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Optional

OUTPUT_FORMATS = {"excel": "PDF to Excel", "word": "PDF to Word", "both": "PDF to Excel and Word"}
DOCUMENT_TYPES = {"general": "General document", "bank_statement": "Bank statement (balance-checked)"}
OCR_MODES = {"auto": "Automatic (recommended)", "always": "Always run OCR", "off": "Off"}
WORD_MODES = {"editable": "Editable document", "layout": "Layout-preserving", "text": "Text extraction"}
SHEET_MODES = {"combine": "Combine continued tables", "per_table": "One sheet per table", "per_page": "One sheet per page"}
WORKBOOK_MODES = {"per_pdf": "One workbook per PDF", "combined": "One combined workbook (sheet per PDF)"}
TABLE_METHODS = {"auto": "Automatic (ruled + aligned)", "lines": "Ruled tables only", "text": "Aligned columns only"}
CONFLICT_POLICIES = {"ask": "Ask me each time", "increment": "Save with a new name",
                     "skip": "Skip the file", "overwrite": "Overwrite (after confirmation)"}
NAMING = {"original": "Same name as the PDF", "suffix": "PDF name + suffix"}


@dataclass
class ConversionSettings:
    output_format: str = "excel"
    document_type: str = "general"         # general | bank_statement
    output_folder: Path = Path(".")
    ocr_mode: str = "auto"
    ocr_language: str = "eng"
    ocr_dpi: int = 300
    ocr_timeout_seconds: int = 180
    page_range: Optional[list[tuple[int, int]]] = None
    word_mode: str = "editable"
    sheet_mode: str = "combine"
    workbook_mode: str = "per_pdf"
    table_method: str = "auto"
    include_text_sheet: bool = True
    include_page_refs: bool = True
    preserve_page_breaks: bool = True
    preserve_scanned_images: bool = False
    convert_dates: bool = True
    indian_number_format: bool = True
    naming: str = "original"
    output_suffix: str = "_Converted"
    subfolder_per_pdf: bool = False
    conflict_policy: str = "ask"
    min_free_disk_mb: int = 50

    @property
    def want_excel(self) -> bool:
        return self.output_format in ("excel", "both")

    @property
    def want_word(self) -> bool:
        return self.output_format in ("word", "both")

    @property
    def bank_mode(self) -> bool:
        return self.want_excel and self.document_type == "bank_statement"

    @classmethod
    def from_config(cls, cfg: dict[str, Any], **overrides: Any) -> "ConversionSettings":
        names = {f.name for f in fields(cls)}
        values = {k: v for k, v in cfg.items() if k in names}
        values.update(overrides)
        if "output_folder" in values:
            values["output_folder"] = Path(values["output_folder"] or ".")
        return cls(**values)
