"""Line icons drawn from inline SVG so they can be tinted to the theme colours."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

ASSETS = Path(__file__).resolve().parent.parent / "assets"

_P = '<path d="{}"/>'
_DOC = _P.format("M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z") + _P.format("M14 2v6h6")
_FOLDER = _P.format("M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z")

ICONS: dict[str, str] = {
    # general
    "home": _P.format("M3 10l9-7 9 7v10a2 2 0 0 1-2 2h-4v-6H9v6H5a2 2 0 0 1-2-2z"),
    "search": '<circle cx="11" cy="11" r="7"/>' + _P.format("M21 21l-4.3-4.3"),
    "file-plus": _DOC + _P.format("M12 18v-6") + _P.format("M9 15h6"),
    "folder-plus": _FOLDER + _P.format("M12 10v6") + _P.format("M9 13h6"),
    "folder-open": _P.format("M3 19V7a2 2 0 0 1 2-2h4l2 2h7a2 2 0 0 1 2 2v1")
                   + _P.format("M3 19l2.6-7.6A2 2 0 0 1 7.5 10H21l-2.6 8.6A2 2 0 0 1 16.5 20H5a2 2 0 0 1-2-1z"),
    "trash": _P.format("M3 6h18") + _P.format("M8 6V4h8v2") + _P.format("M19 6l-1 14H6L5 6"),
    "clear": _P.format("M18 6L6 18") + _P.format("M6 6l12 12"),
    "play": '<path d="M7 4l13 8-13 8z" fill="{color}"/>',
    "chevron-down": _P.format("M6 9l6 6 6-6"),
    "chevron-right": _P.format("M9 6l6 6-6 6"),
    "upload": _P.format("M12 15V3") + _P.format("M7 8l5-5 5 5") + _P.format("M5 21h14"),
    "help": '<circle cx="12" cy="12" r="10"/>' + _P.format("M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3") + _P.format("M12 17h.01"),
    "info": '<circle cx="12" cy="12" r="10"/>' + _P.format("M12 16v-4") + _P.format("M12 8h.01"),
    "shield": _P.format("M12 2l8 3v6c0 5-3.5 9-8 11-4.5-2-8-6-8-11V5z") + _P.format("M9 12l2 2 4-4"),
    "grid": '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/>'
            '<rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
    # utilities
    "merge": '<circle cx="6" cy="5" r="2"/><circle cx="6" cy="19" r="2"/><circle cx="18" cy="12" r="2"/>'
             + _P.format("M6 7v10") + _P.format("M6 7c0 5 4 5 10 5"),
    "split": _P.format("M16 3h5v5") + _P.format("M8 3H3v5") + _P.format("M12 22v-8.3a4 4 0 0 0-1.2-2.8L3 3")
             + _P.format("M21 3l-7.8 7.8"),
    "extract": _DOC + _P.format("M9 13h6") + _P.format("M12 10v6"),
    "hash": _P.format("M4 9h16") + _P.format("M4 15h16") + _P.format("M10 3L8 21") + _P.format("M16 3l-2 18"),
    "rearrange": _P.format("M7 4v16") + _P.format("M3 8l4-4 4 4") + _P.format("M17 20V4") + _P.format("M13 16l4 4 4-4"),
    "rotate": _P.format("M21 12a9 9 0 1 1-2.6-6.4") + _P.format("M21 3v6h-6"),
    "image": '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/>' + _P.format("M21 15l-5-5L5 21"),
    "images-pdf": '<rect x="2" y="6" width="13" height="13" rx="2"/>' + _P.format("M2 15l3-3 4 4")
                  + _P.format("M17 4h3a2 2 0 0 1 2 2v12") + _P.format("M18 9h-1"),
    "lock": '<rect x="4" y="11" width="16" height="10" rx="2"/>' + _P.format("M8 11V7a4 4 0 0 1 8 0v4"),
    "unlock": '<rect x="4" y="11" width="16" height="10" rx="2"/>' + _P.format("M8 11V7a4 4 0 0 1 7.9-1"),
    "markdown": '<rect x="2" y="5" width="20" height="14" rx="2"/>' + _P.format("M6 15V9l3 3 3-3v6")
                + _P.format("M17 9v6") + _P.format("M15 13l2 2 2-2"),
    # conversion
    "sheet": '<rect x="3" y="3" width="18" height="18" rx="2"/>' + _P.format("M3 9h18") + _P.format("M3 15h18")
             + _P.format("M9 3v18"),
    "doc": _DOC + _P.format("M8 13h8") + _P.format("M8 17h8") + _P.format("M8 9h2"),
    "layers": _P.format("M12 2l10 5-10 5L2 7z") + _P.format("M2 17l10 5 10-5") + _P.format("M2 12l10 5 10-5"),
    "bank": _P.format("M3 21h18") + _P.format("M3 10h18") + _P.format("M5 6l7-3 7 3") + _P.format("M5 10v11")
            + _P.format("M19 10v11") + _P.format("M9 14v4") + _P.format("M12 14v4") + _P.format("M15 14v4"),
    # redaction
    "redact": '<rect x="3" y="4" width="18" height="16" rx="2"/>'
              '<rect x="6" y="8" width="12" height="3" fill="{color}"/>' + _P.format("M6 15h7"),
    "find": _DOC + '<circle cx="11" cy="14" r="3"/>' + _P.format("M13.2 16.2L15.5 18.5"),
    "sparkles": _P.format("M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z") + _P.format("M19 3v4")
                + _P.format("M17 5h4"),
    "eye": _P.format("M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z") + '<circle cx="12" cy="12" r="3"/>',
    "check-square": '<rect x="3" y="3" width="18" height="18" rx="2"/>' + _P.format("M8 12l3 3 5-6"),
    "verify": _P.format("M12 2l8 3v6c0 5-3.5 9-8 11-4.5-2-8-6-8-11V5z") + '<circle cx="11" cy="11" r="3"/>'
              + _P.format("M13.2 13.2L15.5 15.5"),
}


def svg_markup(name: str, color: str, stroke: float = 2.0) -> str:
    body = ICONS[name].replace("{color}", color)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
            f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">{body}</svg>')


def _render(svg: str, size: int) -> QPixmap:
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return pixmap


@lru_cache(maxsize=512)
def icon(name: str, color: str = "#0B1E3D", disabled_color: str = "#A3ACBA") -> QIcon:
    result = QIcon()
    for size in (16, 20, 24, 32, 48):
        result.addPixmap(_render(svg_markup(name, color), size), QIcon.Mode.Normal)
        result.addPixmap(_render(svg_markup(name, disabled_color), size), QIcon.Mode.Disabled)
    return result


def pixmap(name: str, color: str, size: int) -> QPixmap:
    return _render(svg_markup(name, color), size)


def app_icon() -> QIcon:
    for candidate in (ASSETS / "app_icon.ico", ASSETS / "app_icon.png"):
        if candidate.exists():
            return QIcon(str(candidate))
    return icon("grid")
