"""Left navigation: Home, tool search and three sliding (accordion) sections.

Opening a section slides it open and closes the section that was open before,
so only one group of tools is visible at a time. While searching, every
section with a match is shown and non-matching tools are hidden.
"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QSize, Qt, Signal
from PySide6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
                               QSizePolicy, QToolButton, QVBoxLayout, QWidget)

from . import theme
from .catalog import SECTIONS, Section
from .icons import icon

ANIMATION_MS = 220


def _repolish(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class AccordionSection(QWidget):
    toggled = Signal(str, bool)          # section id, now open
    tool_clicked = Signal(str)

    def __init__(self, section: Section, group: QButtonGroup):
        super().__init__()
        self.section = section
        self.is_open = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)

        self.header = QToolButton()
        self.header.setObjectName("sectionHeader")
        self.header.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.header.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.header.setIconSize(QSize(18, 18))
        self.header.setText(section.name.replace("&", "&&"))     # '&' would mark a shortcut key
        self.header.setToolTip(section.blurb)
        self.header.setMinimumHeight(40)
        head_lay = QHBoxLayout(self.header)
        head_lay.setContentsMargins(0, 0, 10, 0)
        head_lay.addStretch()
        self.count = QLabel(str(len(section.tools)))
        self.count.setObjectName("sectionCount")
        self.count.setFixedHeight(20)
        self.count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.count.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        head_lay.addWidget(self.count, 0, Qt.AlignmentFlag.AlignVCenter)
        self.chevron = QLabel()
        self.chevron.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        head_lay.addWidget(self.chevron, 0, Qt.AlignmentFlag.AlignVCenter)
        self.header.clicked.connect(lambda: self.toggled.emit(section.id, not self.is_open))
        lay.addWidget(self.header)

        self.body = QWidget()
        body_lay = QVBoxLayout(self.body)
        body_lay.setContentsMargins(0, 2, 0, 6)
        body_lay.setSpacing(0)
        self.items: dict[str, QPushButton] = {}
        for tool in section.tools:
            btn = QPushButton(tool.name.replace("&", "&&"))
            btn.setObjectName("toolItem")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(tool.summary)
            btn.clicked.connect(lambda _=False, t=tool.id: self.tool_clicked.emit(t))
            group.addButton(btn)
            body_lay.addWidget(btn)
            self.items[tool.id] = btn
        lay.addWidget(self.body)
        self.body.setMaximumHeight(0)
        self.anim = QPropertyAnimation(self.body, b"maximumHeight", self)
        self.anim.setDuration(ANIMATION_MS)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._paint_header()

    def _paint_header(self) -> None:
        open_ = self.is_open
        self.header.setProperty("open", open_)
        self.count.setProperty("open", open_)
        _repolish(self.header)
        _repolish(self.count)
        color = theme.WHITE if open_ else self.section.color
        self.header.setIcon(icon(self.section.icon, color))
        self.chevron.setPixmap(icon("chevron-down" if open_ else "chevron-right",
                                    theme.WHITE if open_ else theme.MUTED).pixmap(14, 14))

    def set_open(self, open_: bool, animate: bool = True) -> None:
        self.is_open = open_
        self._paint_header()
        target = self.body.sizeHint().height() if open_ else 0
        self.anim.stop()
        if animate:
            self.anim.setStartValue(self.body.maximumHeight())
            self.anim.setEndValue(target)
            self.anim.start()
        else:
            self.body.setMaximumHeight(target)

    def filter(self, query: str) -> int:
        """Show only tools matching the query; returns the number of matches."""
        q = query.strip().lower()
        shown = 0
        for tool in self.section.tools:
            match = not q or q in tool.name.lower() or q in tool.summary.lower() or q in self.section.name.lower()
            self.items[tool.id].setVisible(match)
            shown += match
        self.count.setText(str(shown if q else len(self.section.tools)))
        return shown


class Sidebar(QFrame):
    home_clicked = Signal()
    tool_selected = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("sidebar")
        self.setFixedWidth(286)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 14, 12, 10)
        outer.setSpacing(10)

        self.search = QLineEdit()
        self.search.setObjectName("toolSearch")
        self.search.setPlaceholderText("Search tools…  (e.g. merge, PAN, Excel)")
        self.search.addAction(icon("search", theme.MUTED), QLineEdit.ActionPosition.LeadingPosition)
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._on_search)
        outer.addWidget(self.search)

        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.home = QToolButton()
        self.home.setObjectName("homeButton")
        self.home.setText("Home")
        self.home.setIcon(icon("home", theme.NAVY))
        self.home.setIconSize(QSize(18, 18))
        self.home.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.home.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.home.setCheckable(True)
        self.home.setCursor(Qt.CursorShape.PointingHandCursor)
        self.home.clicked.connect(self.home_clicked.emit)
        self.group.addButton(self.home)
        outer.addWidget(self.home)

        caption = QLabel("TOOLS")
        caption.setObjectName("sidebarCaption")
        outer.addWidget(caption)

        holder = QWidget()
        holder_lay = QVBoxLayout(holder)
        holder_lay.setContentsMargins(0, 0, 0, 0)
        holder_lay.setSpacing(6)
        self.sections: dict[str, AccordionSection] = {}
        for section in SECTIONS:
            acc = AccordionSection(section, self.group)
            acc.toggled.connect(self._on_toggle)
            acc.tool_clicked.connect(self.tool_selected.emit)
            holder_lay.addWidget(acc)
            self.sections[section.id] = acc
        self.no_match = QLabel("No tool matches your search.")
        self.no_match.setObjectName("sidebarCaption")
        self.no_match.setVisible(False)
        holder_lay.addWidget(self.no_match)
        holder_lay.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(holder)
        outer.addWidget(scroll, 1)
        self._open_before_search: str | None = None

    # ------------------------------------------------------------ behaviour

    def open_only(self, section_id: str | None, animate: bool = True) -> None:
        for sid, acc in self.sections.items():
            want = sid == section_id
            if acc.is_open != want:
                acc.set_open(want, animate)

    def _on_toggle(self, section_id: str, open_: bool) -> None:
        if self.search.text():
            self.search.clear()
        self.open_only(section_id if open_ else None)

    def select_tool(self, tool_id: str, section_id: str) -> None:
        self.open_only(section_id)
        self.sections[section_id].items[tool_id].setChecked(True)

    def select_home(self) -> None:
        self.home.setChecked(True)

    def _on_search(self, text: str) -> None:
        if text and self._open_before_search is None:
            self._open_before_search = next((s for s, a in self.sections.items() if a.is_open), "")
        total = 0
        for acc in self.sections.values():
            n = acc.filter(text)
            total += n
            acc.setVisible(not text or n > 0)          # hide sections without a match
            if text:
                acc.set_open(n > 0, animate=False)
                acc.body.setMaximumHeight(acc.body.sizeHint().height() if n else 0)
        self.no_match.setVisible(bool(text) and total == 0)
        if not text and self._open_before_search is not None:
            self.open_only(self._open_before_search or None, animate=False)
            self._open_before_search = None
