"""Folder lookup for bundled resources (a 'tesseract' folder next to the application).

PDF Converter Pro's full configuration layer (config.json, user_settings.json) is not
needed here: PDF Play Station passes every setting directly from the tool page."""

from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_root() -> Path:
    """Folder that contains the program (project folder or the .exe folder)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def resource_path(*parts: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", app_root())) if is_frozen() else app_root()
    return base.joinpath(*parts)
