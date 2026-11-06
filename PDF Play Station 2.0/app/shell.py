"""Main window: header, sliding sidebar, page area and footer."""

from __future__ import annotations

from PySide6.QtCore import QSettings, QSize, Qt
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton,
                               QStackedWidget, QVBoxLayout, QWidget)

from . import APP_BYLINE, APP_NAME, APP_STAGE, APP_TAGLINE, APP_VERSION, OFFLINE_NOTE, SETTINGS_APP, SETTINGS_ORG
from . import theme
from .catalog import ALL_TOOLS, SECTIONS
from .icons import app_icon, icon, pixmap
from .pages import HomePage, ToolPage
from .sidebar import Sidebar

REDACTION_MODES = ("manual", "find", "smart", "review", "apply")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        self.resize(1380, 880)
        self.setMinimumSize(1120, 720)

        central = QWidget()
        central.setObjectName("central")
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._header())

        middle = QHBoxLayout()
        middle.setContentsMargins(0, 0, 0, 0)
        middle.setSpacing(0)
        self.sidebar = Sidebar()
        self.sidebar.home_clicked.connect(self.show_home)
        self.sidebar.tool_selected.connect(self.show_tool)
        middle.addWidget(self.sidebar)
        self.stack = QStackedWidget()
        self.home = HomePage()
        self.home.open_tool.connect(self.show_tool)
        self.home.open_section.connect(self.open_section)
        self.stack.addWidget(self.home)
        middle.addWidget(self.stack, 1)
        root.addLayout(middle, 1)
        root.addWidget(self._footer())
        self.setCentralWidget(central)

        # Tool pages are created the first time they are opened, so start-up
        # stays fast however many tools are added.
        self.pages: dict[str, ToolPage] = {}
        self.show_home()
        self.settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        geometry = self.settings.value("window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)

    def closeEvent(self, event) -> None:
        red = self.pages.get("redaction")
        if red is not None and not red.confirm_discard():
            event.ignore()
            return
        self.settings.setValue("window/geometry", self.saveGeometry())
        super().closeEvent(event)

    # ------------------------------------------------------------ chrome

    def _header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("header")
        lay = QHBoxLayout(header)
        lay.setContentsMargins(22, 12, 22, 12)
        lay.setSpacing(14)
        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(QSize(48, 48)))
        lay.addWidget(logo)
        text = QVBoxLayout()
        text.setSpacing(0)
        title = QLabel(APP_NAME)
        title.setObjectName("appTitle")
        byline = QLabel(APP_BYLINE)
        byline.setObjectName("headerByline")
        text.addWidget(title)
        text.addWidget(byline)
        lay.addLayout(text)
        lay.addStretch()
        tagline = QLabel(APP_TAGLINE)
        tagline.setObjectName("headerBadge")
        lay.addWidget(tagline)
        return header

    def _footer(self) -> QFrame:
        footer = QFrame()
        footer.setObjectName("footer")
        lay = QHBoxLayout(footer)
        lay.setContentsMargins(20, 6, 20, 6)
        version = QLabel(f"{APP_NAME} v{APP_VERSION}  ·  {APP_STAGE}")
        version.setObjectName("footerText")
        lay.addWidget(version)
        for text, ic, handler in (("Help", "help", self._help), ("About", "info", self._about)):
            b = QPushButton(icon(ic, theme.MUTED), text)
            b.setObjectName("footerButton")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(handler)
            lay.addWidget(b)
        lay.addStretch()
        shield = QLabel()
        shield.setPixmap(pixmap("shield", theme.SUCCESS, 15))
        lay.addWidget(shield)
        offline = QLabel(OFFLINE_NOTE)
        offline.setObjectName("footerOffline")
        lay.addWidget(offline)
        return footer

    # ------------------------------------------------------------ navigation

    def show_home(self) -> None:
        self.stack.setCurrentWidget(self.home)
        self.sidebar.select_home()

    def show_tool(self, tool_id: str) -> None:
        section, tool = ALL_TOOLS[tool_id]
        if tool_id in REDACTION_MODES:
            page = self._redaction_page()
            page.set_mode(tool_id)
        else:
            page = self.pages.get(tool_id)
            if page is None:
                page = ToolPage(section, tool)
                self.pages[tool_id] = page
                self.stack.addWidget(page)
        self.stack.setCurrentWidget(page)
        self.sidebar.select_tool(tool_id, section.id)

    def _redaction_page(self):
        """Manual / Find / Smart / Review / Apply share one page (one document, one list of marks)."""
        page = self.pages.get("redaction")
        if page is None:
            from .redaction_ui import RedactionPage
            page = RedactionPage()
            page.mode_changed.connect(lambda m: self.sidebar.select_tool(m, "redaction"))
            page.verify_requested.connect(self._verify_output)
            self.pages["redaction"] = page
            self.stack.addWidget(page)
        return page

    def _verify_output(self, path: str, values: list) -> None:
        self.show_tool("verify")
        self.pages["verify"].prefill([path], {"Values that must not appear": values})

    def open_section(self, section_id: str) -> None:
        section = next(s for s in SECTIONS if s.id == section_id)
        self.show_tool(section.tools[0].id)

    # ------------------------------------------------------------ dialogs

    def _help(self) -> None:
        QMessageBox.information(self, f"{APP_NAME} - Help",
                                "1. Pick a tool on the left (or search for it).\n"
                                "2. Add files - drag and drop works everywhere.\n"
                                "3. Choose the options, then click the button at the bottom right.\n\n"
                                "Sections slide open one at a time; the search box finds any tool.")

    def _about(self) -> None:
        QMessageBox.about(self, f"About {APP_NAME}",
                          f"<h3 style='color:{theme.NAVY}'>{APP_NAME} {APP_VERSION}</h3>"
                          f"<p>{APP_BYLINE}</p>"
                          "<p>PDF utilities, conversion to Excel/Word and secure redaction in one tool.</p>"
                          f"<p><b>{OFFLINE_NOTE}</b><br>All processing happens on this computer.</p>")
