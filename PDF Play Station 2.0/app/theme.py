"""Visual theme, based on the Kirtane & Pandit website palette
(navy #0B1E3D, bronze-gold #B8966E, warm cream #F7F5F0 on white)."""

from __future__ import annotations

NAVY = "#0B1E3D"
NAVY_HOVER = "#1A3566"
NAVY_PRESSED = "#06122A"
GOLD = "#B8966E"
GOLD_DARK = "#6F5A3F"
GOLD_TINT = "#F4EEE6"
CREAM = "#F7F5F0"
CREAM_LIGHT = "#FBFAF7"
WHITE = "#FFFFFF"
TEXT = "#0B1E3D"
MUTED = "#4A5568"
BORDER = "#DADFE7"
BORDER_STRONG = "#B9C1CE"
EXCEL = "#1D6F42"
EXCEL_TINT = "#EAF4EE"
WORD = "#1E4E8C"
WORD_TINT = "#EAF0F8"
ERROR = "#B42318"
ERROR_TINT = "#FDECEA"
WARNING = "#9A5B00"
WARNING_TINT = "#FFF6E5"
SUCCESS = "#1D6F42"
# Highlight for selected / hovered items in dropdowns, lists and menus (navy text on it).
HIGHLIGHT = "#EADFCC"

SANS = "Segoe UI"
SERIF = "Georgia"

STYLESHEET_TEMPLATE = f"""
* {{ font-family: "{SANS}"; font-size: 10pt; color: {TEXT}; }}
QMainWindow, QDialog {{ background: {WHITE}; }}
QWidget#central {{ background: {WHITE}; }}
QToolTip {{ background: {NAVY}; color: {WHITE}; border: none; padding: 6px 8px; }}

/* ---------- header and footer ---------- */
QFrame#header {{ background: {NAVY}; border-bottom: 3px solid {GOLD}; }}
QLabel#appTitle {{ font-family: "{SERIF}"; font-size: 20pt; color: {WHITE}; }}
QLabel#appSubtitle {{ color: #C9D1DE; font-size: 10pt; }}
QLabel#headerBadge {{ color: {GOLD}; font-size: 9pt; letter-spacing: 1px; }}
QFrame#footer {{ background: {CREAM}; border-top: 1px solid {BORDER}; }}
QLabel#footerText {{ color: {MUTED}; font-size: 9pt; }}

/* ---------- cards ---------- */
QFrame[card="true"] {{ background: {WHITE}; border: 1px solid {BORDER}; border-radius: 8px; }}
QLabel[role="cardTitle"] {{ font-family: "{SERIF}"; font-size: 12.5pt; color: {NAVY}; }}
QLabel[role="hint"] {{ color: {MUTED}; font-size: 9pt; }}
QLabel[role="field"] {{ color: {MUTED}; font-size: 9pt; font-weight: 600; }}
QLabel[role="error"] {{ color: {ERROR}; font-size: 9pt; }}
QLabel[role="warning"] {{ color: {WARNING}; font-size: 9pt; }}
QLabel[role="ok"] {{ color: {SUCCESS}; font-size: 9pt; }}

/* ---------- conversion type tiles ---------- */
QToolButton[tile="true"] {{
    background: {WHITE}; border: 1px solid {BORDER}; border-radius: 8px;
    padding: 10px 12px; font-size: 10.5pt; font-weight: 600; text-align: left;
}}
QToolButton[tile="true"]:hover {{ border-color: {BORDER_STRONG}; background: {CREAM_LIGHT}; }}
QToolButton#tileExcel:checked {{ border: 2px solid {EXCEL}; background: {EXCEL_TINT}; color: {EXCEL}; }}
QToolButton#tileWord:checked {{ border: 2px solid {WORD}; background: {WORD_TINT}; color: {WORD}; }}
QToolButton#tileBoth:checked {{ border: 2px solid {GOLD}; background: {GOLD_TINT}; color: {GOLD_DARK}; }}
QToolButton[tile="true"]:disabled {{ color: {BORDER_STRONG}; }}

/* ---------- buttons ---------- */
QPushButton {{
    background: {WHITE}; border: 1px solid {BORDER_STRONG}; border-radius: 6px;
    padding: 6px 12px; min-height: 20px;
}}
QPushButton:hover {{ background: {CREAM}; border-color: {NAVY}; }}
QPushButton:pressed {{ background: {GOLD_TINT}; }}
QPushButton:disabled {{ color: #9AA3B2; border-color: {BORDER}; background: {CREAM_LIGHT}; }}
QPushButton#primary {{
    background: {NAVY}; color: {WHITE}; border: 1px solid {NAVY};
    font-weight: 600; padding: 8px 22px; font-size: 10.5pt;
}}
QPushButton#primary:hover {{ background: {NAVY_HOVER}; border-color: {GOLD}; }}
QPushButton#primary:pressed {{ background: {NAVY_PRESSED}; }}
QPushButton#primary:disabled {{ background: #8C97AA; border-color: #8C97AA; color: #EEF1F5; }}
QPushButton#danger {{ color: {ERROR}; border-color: #E4A7A1; font-weight: 600; padding: 8px 16px; }}
QPushButton#danger:hover {{ background: {ERROR_TINT}; border-color: {ERROR}; }}
QPushButton#danger:disabled {{ color: #C9A9A6; border-color: {BORDER}; background: {CREAM_LIGHT}; }}
QPushButton#link {{ border: none; background: transparent; color: {WORD}; padding: 2px 4px; text-decoration: underline; }}
QPushButton#link:hover {{ color: {NAVY}; }}
QPushButton#footerButton {{ border: none; background: transparent; color: {MUTED}; padding: 2px 8px; }}
QPushButton#footerButton:hover {{ color: {NAVY}; text-decoration: underline; }}
QToolButton#sectionToggle {{ border: none; background: transparent; font-weight: 600; color: {NAVY}; padding: 4px 0; }}
QToolButton#sectionToggle:hover {{ color: {GOLD_DARK}; }}

/* ---------- inputs ---------- */
QLineEdit, QComboBox, QSpinBox {{
    background: {WHITE}; border: 1px solid {BORDER_STRONG}; border-radius: 5px;
    padding: 5px 8px; min-height: 20px; selection-background-color: {HIGHLIGHT}; selection-color: {NAVY};
}}
QLineEdit:focus, QComboBox:focus {{ border: 1px solid {GOLD}; }}
QLineEdit[invalid="true"] {{ border: 1px solid {ERROR}; background: {ERROR_TINT}; }}
QLineEdit:disabled, QComboBox:disabled {{ background: {CREAM_LIGHT}; color: #8C97AA; }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox::down-arrow {{ image: url("{{arrow_url}}"); width: 12px; height: 12px; }}
/* Dropdown lists: the highlighted item is always light cream-gold with navy text,
   never navy on navy (the unreadable highlight of the earlier PDF Play Station). */
QComboBox QAbstractItemView {{
    border: 1px solid {BORDER_STRONG}; background: {WHITE}; color: {TEXT};
    selection-background-color: {HIGHLIGHT}; selection-color: {NAVY}; outline: none; padding: 2px;
}}
QComboBox QAbstractItemView::item {{ min-height: 24px; padding: 2px 8px; color: {TEXT}; }}
QComboBox QAbstractItemView::item:hover,
QComboBox QAbstractItemView::item:selected {{ background: {HIGHLIGHT}; color: {NAVY}; }}
QListView, QTreeView, QListWidget, QTreeWidget {{
    background: {WHITE}; border: 1px solid {BORDER}; border-radius: 6px;
    selection-background-color: {HIGHLIGHT}; selection-color: {NAVY}; outline: none;
}}
QListView::item:selected, QTreeView::item:selected, QListWidget::item:selected,
QTreeWidget::item:selected {{ background: {HIGHLIGHT}; color: {NAVY}; }}
QListView::item:hover, QTreeView::item:hover {{ background: {CREAM}; color: {NAVY}; }}
QMenu {{ background: {WHITE}; border: 1px solid {BORDER_STRONG}; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; color: {TEXT}; }}
QMenu::item:selected {{ background: {HIGHLIGHT}; color: {NAVY}; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {BORDER_STRONG}; border-radius: 3px; background: {WHITE}; }}
QCheckBox::indicator:checked {{ background: {NAVY}; border-color: {NAVY}; image: url("{{check_url}}"); }}
QCheckBox::indicator:hover {{ border-color: {GOLD}; }}

/* ---------- table ---------- */
QTableWidget, QTableView {{
    background: {WHITE}; border: 1px solid {BORDER}; border-radius: 6px;
    gridline-color: #EEF0F4; selection-background-color: {GOLD_TINT}; selection-color: {NAVY};
    alternate-background-color: {CREAM_LIGHT};
}}
QHeaderView::section {{
    background: {CREAM}; color: {MUTED}; border: none; border-bottom: 1px solid {BORDER};
    padding: 6px 8px; font-weight: 600; font-size: 9pt;
}}
QTableCornerButton::section {{ background: {CREAM}; border: none; }}

/* ---------- progress ---------- */
QProgressBar {{
    background: #E9ECF1; border: none; border-radius: 6px; height: 12px; text-align: center;
    color: {NAVY}; font-size: 8.5pt; font-weight: 600;
}}
QProgressBar::chunk {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {NAVY}, stop:1 {NAVY_HOVER});
                       border-radius: 6px; }}
QLabel[counter="true"] {{ border-radius: 10px; padding: 3px 10px; font-size: 9pt; font-weight: 600; }}
QLabel#countOk {{ background: {EXCEL_TINT}; color: {SUCCESS}; }}
QLabel#countFail {{ background: {ERROR_TINT}; color: {ERROR}; }}
QLabel#countSkip {{ background: {WARNING_TINT}; color: {WARNING}; }}
QLabel#countPending {{ background: #EEF1F6; color: {MUTED}; }}

QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #C8CED8; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {GOLD}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #C8CED8; border-radius: 4px; min-width: 30px; }}

QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 6px; top: -1px; }}
QTabBar::tab {{ background: {CREAM}; border: 1px solid {BORDER}; padding: 6px 14px; margin-right: 2px;
               border-top-left-radius: 6px; border-top-right-radius: 6px; color: {MUTED}; }}
QTabBar::tab:selected {{ background: {WHITE}; color: {NAVY}; border-bottom-color: {WHITE}; font-weight: 600; }}
QFrame#notice {{ background: {WARNING_TINT}; border: 1px solid #F1D9A8; border-radius: 6px; }}
QFrame#statTile {{ background: {CREAM_LIGHT}; border: 1px solid {BORDER}; border-radius: 8px; }}
QLabel#statValue {{ font-family: "{SERIF}"; font-size: 18pt; color: {NAVY}; }}
QLabel#statLabel {{ color: {MUTED}; font-size: 8.5pt; }}
/* ---------- PDF Play Station: sidebar ---------- */
QFrame#sidebar {{ background: {CREAM}; border-right: 1px solid {BORDER}; }}
QLineEdit#toolSearch {{ background: {WHITE}; border: 1px solid {BORDER_STRONG}; border-radius: 16px; padding: 6px 12px; }}
QLineEdit#toolSearch:focus {{ border: 1px solid {GOLD}; }}
QToolButton#homeButton, QToolButton#sectionHeader {{
    background: transparent; border: none; border-radius: 8px; padding: 9px 10px;
    font-size: 10.5pt; font-weight: 600; color: {NAVY}; text-align: left;
}}
QToolButton#homeButton:hover, QToolButton#sectionHeader:hover {{ background: #EFEBE3; }}
QToolButton#homeButton:checked {{ background: {WHITE}; border: 1px solid {BORDER}; }}
QToolButton#sectionHeader[open="true"] {{ background: {NAVY}; color: {WHITE}; }}
QLabel#sectionCount {{ background: #E6E1D6; color: {GOLD_DARK}; border-radius: 9px; padding: 1px 7px;
                      font-size: 8.5pt; font-weight: 600; }}
QLabel#sectionCount[open="true"] {{ background: {GOLD}; color: {NAVY}; }}
QPushButton#toolItem {{
    background: transparent; border: none; border-left: 3px solid transparent; border-radius: 0;
    text-align: left; padding: 7px 10px 7px 34px; color: {MUTED}; font-size: 10pt; min-height: 18px;
}}
QPushButton#toolItem:hover {{ background: #EFEBE3; color: {NAVY}; }}
QPushButton#toolItem:checked {{ background: {WHITE}; color: {NAVY}; font-weight: 600; border-left: 3px solid {GOLD}; }}
QLabel#sidebarCaption {{ color: {MUTED}; font-size: 8.5pt; letter-spacing: 1px; }}

/* ---------- pages ---------- */
QLabel#pageTitle {{ font-family: "{SERIF}"; font-size: 19pt; color: {NAVY}; }}
QLabel#pageBreadcrumb {{ color: {GOLD_DARK}; font-size: 9pt; font-weight: 600; letter-spacing: 0.5px; }}
QLabel#pageDescription {{ color: {MUTED}; font-size: 10.5pt; }}
QLabel#stepChip {{ background: {CREAM}; border: 1px solid {BORDER}; border-radius: 13px; padding: 4px 12px;
                  color: {NAVY}; font-size: 9pt; font-weight: 600; }}
QLabel#previewBadge {{ background: {GOLD_TINT}; color: {GOLD_DARK}; border: 1px solid #E4D5C0; border-radius: 10px;
                      padding: 2px 9px; font-size: 8.5pt; font-weight: 600; }}
QFrame#sectionCard {{ background: {WHITE}; border: 1px solid {BORDER}; border-radius: 10px; }}
QFrame#sectionCard:hover {{ border: 1px solid {GOLD}; background: {CREAM_LIGHT}; }}
QLabel#cardHeading {{ font-family: "{SERIF}"; font-size: 14pt; color: {NAVY}; }}
QPushButton#chip {{ background: {WHITE}; border: 1px solid {BORDER_STRONG}; border-radius: 15px; padding: 5px 14px; }}
QPushButton#chip:hover {{ border-color: {GOLD}; background: {GOLD_TINT}; }}
QFrame#workspace {{ background: #F1F3F7; border: 1px dashed {BORDER_STRONG}; border-radius: 8px; }}
QLabel#headerByline {{ color: {GOLD}; font-size: 9.5pt; font-style: italic; }}
QToolButton#modeButton {{ background: {CREAM}; border: 1px solid {BORDER}; border-radius: 15px;
                          padding: 5px 14px; color: {NAVY}; font-size: 9.5pt; font-weight: 600; }}
QToolButton#modeButton:hover {{ border-color: {GOLD}; background: {GOLD_TINT}; }}
QToolButton#modeButton:checked {{ background: {NAVY}; color: {WHITE}; border-color: {NAVY}; }}
QLabel#footerOffline {{ color: {SUCCESS}; font-size: 9pt; font-weight: 600; }}
"""

def stylesheet(check_icon_path: str) -> str:
    """Final stylesheet; the checkbox tick and dropdown arrow are SVG files in the same folder."""
    arrow = check_icon_path.replace("check.svg", "chevron-down.svg")
    return (STYLESHEET_TEMPLATE.replace("{check_url}", check_icon_path.replace("\\", "/"))
            .replace("{arrow_url}", arrow.replace("\\", "/")))


def palette():
    """Application palette. Some Qt widgets (combo pop-ups in particular) paint the
    highlighted item from the palette rather than the stylesheet, so the readable
    highlight is set here as well."""
    from PySide6.QtGui import QColor, QPalette
    pal = QPalette()
    for role, colour in ((QPalette.ColorRole.Window, WHITE), (QPalette.ColorRole.Base, WHITE),
                         (QPalette.ColorRole.AlternateBase, CREAM_LIGHT), (QPalette.ColorRole.Text, TEXT),
                         (QPalette.ColorRole.WindowText, TEXT), (QPalette.ColorRole.Button, WHITE),
                         (QPalette.ColorRole.ButtonText, TEXT), (QPalette.ColorRole.ToolTipBase, NAVY),
                         (QPalette.ColorRole.ToolTipText, WHITE), (QPalette.ColorRole.PlaceholderText, "#7A8494"),
                         (QPalette.ColorRole.Highlight, HIGHLIGHT), (QPalette.ColorRole.HighlightedText, NAVY)):
        pal.setColor(role, QColor(colour))
    for group in (QPalette.ColorGroup.Inactive,):
        pal.setColor(group, QPalette.ColorRole.Highlight, QColor(HIGHLIGHT))
        pal.setColor(group, QPalette.ColorRole.HighlightedText, QColor(NAVY))
    return pal
