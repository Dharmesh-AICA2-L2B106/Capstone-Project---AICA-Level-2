"""Home page and the single tool-page template used by every tool.

Every tool page has the same three steps so users learn the layout once:
    1 Add files   ->   2 Choose options   ->   3 Run
Rearrange Pages and the redaction tools replace the file list with a page workspace.
Running a tool: passwords are asked for first (kept in memory only), the job runs
in the background with a progress bar and Cancel, and the result panel lists the
new files with an Open folder button.
"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QPainter
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                               QFrame, QGridLayout, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit,
                               QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QSpinBox,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from . import theme
from .catalog import POPULAR, SECTIONS, ALL_TOOLS, Option, Section, Tool
from .icons import icon, pixmap

EXTENSIONS = {"pdf": (".pdf",), "images": (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"),
              "markdown": (".md", ".markdown", ".txt")}
FILTERS = {"pdf": "PDF files (*.pdf)", "images": "Images (*.png *.jpg *.jpeg *.tif *.tiff *.bmp)",
           "markdown": "Markdown (*.md *.markdown *.txt)"}


def _label(text: str, obj: str = "", role: str = "", wrap: bool = True) -> QLabel:
    lbl = QLabel(text)
    if obj:
        lbl.setObjectName(obj)
    if role:
        lbl.setProperty("role", role)
    lbl.setWordWrap(wrap)
    return lbl


def _card(title: str, icon_name: str) -> tuple[QFrame, QVBoxLayout, QHBoxLayout]:
    frame = QFrame()
    frame.setProperty("card", True)
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(16, 14, 16, 16)
    lay.setSpacing(10)
    head = QHBoxLayout()
    ic = QLabel()
    ic.setPixmap(pixmap(icon_name, theme.GOLD_DARK, 18))
    head.addWidget(ic)
    head.addWidget(_label(title, role="cardTitle", wrap=False))
    head.addStretch()
    lay.addLayout(head)
    return frame, lay, head


def _short_folder(folder: Path, keep: int = 2) -> str:
    """'C:\\Users\\Admin\\...\\Clients\\2025' - drive plus the last folders; full path in the tooltip."""
    parts = folder.parts
    if len(parts) <= keep + 2:
        return str(folder)
    return str(Path(parts[0], *parts[1:2], "…", *parts[-keep:]))


def _repolish(w: QWidget) -> None:
    w.style().unpolish(w)
    w.style().polish(w)


# ================================================================ home

class HomePage(QScrollArea):
    open_tool = Signal(str)
    open_section = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(36, 28, 36, 28)
        lay.setSpacing(18)

        lay.addWidget(_label("WELCOME", "pageBreadcrumb", wrap=False))
        lay.addWidget(_label("What would you like to do today?", "pageTitle"))
        lay.addWidget(_label("Pick a tool on the left, or start from one of the sections below. "
                             "Everything runs on this computer - your documents never leave it.", "pageDescription"))

        grid = QGridLayout()
        grid.setSpacing(16)
        for col, section in enumerate(SECTIONS):
            grid.addWidget(self._section_card(section), 0, col)
        lay.addLayout(grid)

        lay.addWidget(_label("POPULAR TOOLS", "pageBreadcrumb", wrap=False))
        chips = QHBoxLayout()
        chips.setSpacing(10)
        for tool_id in POPULAR:
            section, tool = ALL_TOOLS[tool_id]
            chip = QPushButton(icon(tool.icon, section.color), tool.name.replace("&", "&&"))
            chip.setObjectName("chip")
            chip.setIconSize(QSize(16, 16))
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.clicked.connect(lambda _=False, t=tool_id: self.open_tool.emit(t))
            chips.addWidget(chip)
        chips.addStretch()
        lay.addLayout(chips)

        how, how_lay, _ = _card("How every tool works", "info")
        steps = QHBoxLayout()
        for n, (title, text) in enumerate([
                ("Add files", "Drag PDFs onto the list, or use Add files / Add folder."),
                ("Choose options", "Each tool shows only the options it needs."),
                ("Run", "Results are saved to the folder you choose. Originals are never changed.")], start=1):
            box = QVBoxLayout()
            box.setAlignment(Qt.AlignmentFlag.AlignTop)
            box.addWidget(_label(f"{n}  {title}", "stepChip", wrap=False), 0, Qt.AlignmentFlag.AlignLeft)
            box.addWidget(_label(text, role="hint"))
            steps.addLayout(box, 1)
        how_lay.addLayout(steps)
        lay.addWidget(how)
        lay.addStretch()
        self.setWidget(body)

    def _section_card(self, section: Section) -> QFrame:
        card = QFrame()
        card.setObjectName("sectionCard")
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card.setMinimumHeight(220)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(8)
        top = QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(pixmap(section.icon, section.color, 30))
        top.addWidget(ic)
        top.addStretch()
        top.addWidget(_label(f"{len(section.tools)} tools", "previewBadge", wrap=False))
        lay.addLayout(top)
        lay.addWidget(_label(section.name, "cardHeading"))
        lay.addWidget(_label(section.blurb, role="hint"))
        names = ", ".join(t.name for t in section.tools[:4]) + ("…" if len(section.tools) > 4 else "")
        lay.addWidget(_label(names, role="field"))
        lay.addStretch()
        open_btn = QPushButton("Open section  ›")
        open_btn.setObjectName("link")
        open_btn.clicked.connect(lambda: self.open_section.emit(section.id))
        lay.addWidget(open_btn, 0, Qt.AlignmentFlag.AlignLeft)
        card.mousePressEvent = lambda e, s=section.id: self.open_section.emit(s)
        return card


# ================================================================ files

class FileList(QTableWidget):
    """Shared file queue with drag-and-drop, ordering and an empty-state hint."""

    changed = Signal()

    def __init__(self, accepts: str):
        super().__init__(0, 3)
        self.accepts = accepts
        self.setHorizontalHeaderLabels(["File name", "Size", "Location"])
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.setShowGrid(False)
        self.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(32)
        hdr = self.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.setColumnWidth(1, 80)
        self.paths: list[Path] = []

    def _fill_row(self, r: int, f: Path) -> None:
        name = QTableWidgetItem(icon("doc", theme.ERROR if self.accepts == "pdf" else theme.WORD), f.name)
        name.setToolTip(str(f))
        self.setItem(r, 0, name)
        try:
            size = f.stat().st_size
            text = f"{size / 1024:.0f} KB" if size < 1024 ** 2 else f"{size / 1024 ** 2:.1f} MB"
        except OSError:
            text = "-"
        self.setItem(r, 1, QTableWidgetItem(text))
        loc = QTableWidgetItem(_short_folder(f.parent))
        loc.setToolTip(str(f.parent))
        self.setItem(r, 2, loc)

    def _rebuild(self) -> None:
        self.setRowCount(len(self.paths))
        for r, f in enumerate(self.paths):
            self._fill_row(r, f)

    def add_paths(self, paths: list[Path]) -> None:
        from .services.common import natural_key
        exts = EXTENSIONS[self.accepts]
        for p in paths:
            files = (sorted((f for f in p.rglob("*") if f.suffix.lower() in exts), key=lambda f: natural_key(f.name))
                     if p.is_dir() else [p])
            for f in files:
                if f.suffix.lower() not in exts or f in self.paths:
                    continue
                self.paths.append(f)
                r = self.rowCount()
                self.insertRow(r)
                self._fill_row(r, f)
        self.changed.emit()

    def remove_selected(self) -> None:
        for r in sorted({i.row() for i in self.selectedIndexes()}, reverse=True):
            self.removeRow(r)
            del self.paths[r]
        self.changed.emit()

    def clear_all(self) -> None:
        self.setRowCount(0)
        self.paths.clear()
        self.changed.emit()

    def move(self, delta: int) -> None:
        rows = sorted({i.row() for i in self.selectedIndexes()}, reverse=delta > 0)
        if not rows:
            return
        moved = []
        for r in rows:
            t = r + delta
            if 0 <= t < len(self.paths) and t not in moved:
                self.paths[r], self.paths[t] = self.paths[t], self.paths[r]
                moved.append(t)
            else:
                moved.append(r)
        self._rebuild()
        self.clearSelection()
        for r in moved:
            self.selectRow(r) if len(moved) == 1 else None
        self.changed.emit()

    def sort_by_name(self) -> None:
        from .services.common import natural_key
        self.paths.sort(key=lambda f: natural_key(f.name))
        self._rebuild()
        self.changed.emit()

    def dragEnterEvent(self, e) -> None:
        e.acceptProposedAction() if e.mimeData().hasUrls() else e.ignore()

    def dragMoveEvent(self, e) -> None:
        self.dragEnterEvent(e)

    def dropEvent(self, e) -> None:
        self.add_paths([Path(u.toLocalFile()) for u in e.mimeData().urls() if u.isLocalFile()])
        e.acceptProposedAction()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self.rowCount():
            return
        p = QPainter(self.viewport())
        rect = self.viewport().rect()
        top = rect.center().y() - 46
        p.drawPixmap(rect.center().x() - 18, top, pixmap("upload", theme.GOLD, 36))
        f = p.font()
        f.setPointSizeF(11)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(theme.NAVY))
        kind = {"pdf": "PDF files", "images": "images", "markdown": "Markdown files"}[self.accepts]
        p.drawText(rect.adjusted(0, top - rect.top() + 46, 0, 0), Qt.AlignmentFlag.AlignHCenter,
                   f"Drag and drop {kind} here")
        f.setBold(False)
        f.setPointSizeF(9.5)
        p.setFont(f)
        p.setPen(QColor(theme.MUTED))
        p.drawText(rect.adjusted(0, top - rect.top() + 70, 0, 0), Qt.AlignmentFlag.AlignHCenter,
                   "or use Add files above")
        p.end()


class Workspace(QFrame):
    """Placeholder for page workspaces that are built in a later stage (redaction)."""

    def __init__(self, kind: str, on_drop=None):
        super().__init__()
        self.setObjectName("workspace")
        self.setMinimumHeight(300)
        self.on_drop = on_drop
        self.setAcceptDrops(on_drop is not None)
        lay = QVBoxLayout(self)
        lay.addStretch()
        ic = QLabel()
        ic.setPixmap(pixmap("redact", theme.BORDER_STRONG, 54))
        ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(ic)
        lbl = _label("The PDF page appears here. Draw boxes over anything that must be removed; "
                     "marked areas are listed on the right for review.", role="hint")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(lbl)
        lay.addStretch()

    def dragEnterEvent(self, e) -> None:
        e.acceptProposedAction() if e.mimeData().hasUrls() else e.ignore()

    def dropEvent(self, e) -> None:
        paths = [Path(u.toLocalFile()) for u in e.mimeData().urls() if u.isLocalFile()]
        if paths and self.on_drop:
            self.on_drop(paths[-1:])
        e.acceptProposedAction()


class ConfirmDialog(QDialog):
    """Shows a plan (e.g. sideways pages found) and asks before anything is saved."""

    def __init__(self, parent, title: str, lines: list[str], ok_text: str):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(560, 420)
        lay = QVBoxLayout(self)
        lay.addWidget(_label("Please check before anything is saved:", role="field"))
        box = QPlainTextEdit("\n".join(lines))
        box.setReadOnly(True)
        lay.addWidget(box, 1)
        buttons = QDialogButtonBox()
        ok = buttons.addButton(ok_text, QDialogButtonBox.ButtonRole.AcceptRole)
        ok.setObjectName("primary")
        buttons.addButton("Cancel", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)


# ================================================================ tool page

class ToolPage(QWidget):
    def __init__(self, section: Section, tool: Tool):
        super().__init__()
        self.section, self.tool = section, tool
        self.passwords: dict[str, str] = {}               # this session only, never saved
        self.runner = None
        self.last_files: list[str] = []
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 20, 28, 16)
        root.setSpacing(12)

        # ---- title block
        crumbs = QHBoxLayout()
        crumbs.addWidget(_label(section.name.upper(), "pageBreadcrumb", wrap=False))
        crumbs.addStretch()
        if not tool.ready:
            crumbs.addWidget(_label("Being built - not connected yet", "previewBadge", wrap=False))
        root.addLayout(crumbs)
        title_row = QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(pixmap(tool.icon, section.color, 32))
        title_row.addWidget(ic)
        title_row.addWidget(_label(tool.name, "pageTitle", wrap=False))
        title_row.addStretch()
        root.addLayout(title_row)
        root.addWidget(_label(tool.summary, "pageDescription"))

        steps = QHBoxLayout()
        steps.setSpacing(8)
        first = "Add a file" if not tool.multi else "Add files"
        for n, text in enumerate([first, "Choose options", tool.action], start=1):
            steps.addWidget(_label(f"{n}  {text}", "stepChip", wrap=False))
            if n < 3:
                arrow = QLabel()
                arrow.setPixmap(pixmap("chevron-right", theme.BORDER_STRONG, 14))
                steps.addWidget(arrow)
        steps.addStretch()
        root.addLayout(steps)

        # ---- body: files (or workspace) + options
        body = QHBoxLayout()
        body.setSpacing(16)
        body.addWidget(self._files_card(), 1)
        body.addWidget(self._options_card())
        root.addLayout(body, 1)

        # ---- result panel (hidden until a job finishes)
        self.result = QFrame()
        self.result.setProperty("card", True)
        rl = QVBoxLayout(self.result)
        rl.setContentsMargins(16, 10, 16, 10)
        head = QHBoxLayout()
        self.result_icon = QLabel()
        head.addWidget(self.result_icon)
        self.result_title = _label("", role="cardTitle")
        head.addWidget(self.result_title, 1)
        self.open_btn = QPushButton(icon("folder-open"), "Open folder")
        self.open_btn.clicked.connect(self._open_folder)
        head.addWidget(self.open_btn)
        close = QPushButton(icon("clear"), "")
        close.setToolTip("Hide")
        close.clicked.connect(lambda: self.result.setVisible(False))
        head.addWidget(close)
        rl.addLayout(head)
        self.result_text = _label("", role="hint")
        self.result_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        rl.addWidget(self.result_text)
        self.result.setVisible(False)
        root.addWidget(self.result)

        # ---- action bar
        bar = QFrame()
        bar.setProperty("card", True)
        bar_lay = QHBoxLayout(bar)
        bar_lay.setContentsMargins(16, 10, 16, 10)
        self.status = _label("Add files to begin.", role="hint", wrap=False)
        bar_lay.addWidget(self.status, 1)
        self.progress = QProgressBar()
        self.progress.setFixedWidth(260)
        self.progress.setVisible(False)
        bar_lay.addWidget(self.progress)
        self.cancel_btn = QPushButton(icon("clear"), "Cancel")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self._cancel)
        bar_lay.addWidget(self.cancel_btn)
        self.run_btn = QPushButton(icon("play", theme.WHITE, "#EEF1F5"), tool.action)
        self.run_btn.setObjectName("primary")
        self.run_btn.setMinimumWidth(200)
        self.run_btn.setEnabled(False)
        self.run_btn.clicked.connect(self._run)
        bar_lay.addWidget(self.run_btn)
        root.addWidget(bar)

    # ------------------------------------------------------------ building

    def _files_card(self) -> QFrame:
        title = {"pages": "Pages", "redact": "Document"}.get(self.tool.workspace, "Files")
        card, lay, head = _card(title, "doc")
        self.count = _label("", role="hint", wrap=False)
        head.addWidget(self.count)
        bar = QHBoxLayout()
        add = QPushButton(icon("file-plus"), "Add file" if not self.tool.multi else "Add files")
        bar.addWidget(add)
        add.clicked.connect(self._add_files)
        if self.tool.multi:
            folder = QPushButton(icon("folder-plus"), "Add folder")
            folder.clicked.connect(self._add_folder)
            bar.addWidget(folder)
        bar.addStretch()
        self.files = FileList(self.tool.accepts)
        if self.tool.ordered:
            for text, ic, slot in (("Up", "chevron-right", lambda: self.files.move(-1)),
                                   ("Down", "chevron-down", lambda: self.files.move(1)),
                                   ("Sort A-Z", "rearrange", self.files.sort_by_name)):
                b = QPushButton(text)
                b.setToolTip({"Up": "Move the selected file up", "Down": "Move the selected file down",
                              "Sort A-Z": "Sort by file name (2 before 10)"}[text])
                b.clicked.connect(slot)
                bar.addWidget(b)
        remove = QPushButton(icon("trash"), "Remove")
        clear = QPushButton(icon("clear"), "Clear")
        bar.addWidget(remove)
        bar.addWidget(clear)
        lay.addLayout(bar)
        self.files.changed.connect(self._files_changed)
        remove.clicked.connect(self.files.remove_selected)
        clear.clicked.connect(self.files.clear_all)
        self.pages_ws = None
        if self.tool.workspace:
            # one document at a time: a compact 'selected file' line instead of a list
            self.files.setVisible(False)
            remove.setVisible(False)
            self.selected = _label("No file selected - add a PDF or drop it on the page area.", role="hint")
            lay.addWidget(self.selected)
            if self.tool.workspace == "pages":
                from .workspace import PageWorkspace
                self.pages_ws = PageWorkspace(self.files.add_paths)
                self.pages_ws.changed.connect(self._ws_changed)
                lay.addWidget(self.pages_ws, 1)
            else:
                lay.addWidget(Workspace(self.tool.workspace, self.files.add_paths), 1)
        else:
            lay.addWidget(self.files, 1)
        return card

    def _options_card(self) -> QWidget:
        card, lay, _ = _card("Options", "grid")
        grid = QGridLayout()
        grid.setVerticalSpacing(8)
        grid.setHorizontalSpacing(10)
        grid.setColumnStretch(1, 1)
        r = 0
        if not self.tool.options and not self.tool.workspace:
            grid.addWidget(_label("No options needed for this tool.", role="hint"), r, 0, 1, 2)
            r += 1
        self.option_widgets: dict[str, QWidget] = {}
        for opt in self.tool.options:
            r = self._add_option(grid, r, opt)
        self._wire_dependencies()
        if self.tool.workspace == "redact":
            grid.addWidget(_label("Marked areas", role="field", wrap=False), r, 0, 1, 2)
            r += 1
            grid.addWidget(_label("No areas marked yet.", role="hint"), r, 0, 1, 2)
            r += 1
        lay.addLayout(grid)
        lay.addSpacing(6)
        lay.addWidget(_label("Save results to", role="field", wrap=False))
        out_row = QHBoxLayout()
        self.out = QLineEdit()
        self.out.setPlaceholderText("Same folder as the original")
        browse = QPushButton(icon("folder-open"), "Browse…")
        browse.clicked.connect(self._browse_out)
        out_row.addWidget(self.out, 1)
        out_row.addWidget(browse)
        lay.addLayout(out_row)
        lay.addWidget(_label("Originals are never changed; existing files are never overwritten - "
                             "a new name such as 'file (2).pdf' is used instead.", role="hint"))
        lay.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(card)
        scroll.setFixedWidth(370)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        return scroll

    def _add_option(self, grid: QGridLayout, r: int, opt: Option) -> int:
        label = _label(opt.label, role="field", wrap=False) if opt.label else None
        if opt.kind == "info":
            note = QFrame()
            note.setObjectName("notice")
            nl = QHBoxLayout(note)
            nl.setContentsMargins(10, 8, 10, 8)
            ic = QLabel()
            ic.setPixmap(pixmap("info", theme.WARNING, 16))
            nl.addWidget(ic, 0, Qt.AlignmentFlag.AlignTop)
            nl.addWidget(_label(str(opt.default)), 1)
            grid.addWidget(note, r, 0, 1, 2)
            return r + 1
        if opt.kind == "check":
            # A QCheckBox cannot wrap its text, and a long label would widen the whole
            # Options panel; so the label is a wrapping QLabel that toggles the box.
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(8)
            chk = QCheckBox()
            chk.setChecked(bool(opt.default))
            text = _label(opt.label)
            text.setCursor(Qt.CursorShape.PointingHandCursor)
            text.mousePressEvent = lambda _e, c=chk: c.toggle() if c.isEnabled() else None
            rl.addWidget(chk, 0, Qt.AlignmentFlag.AlignTop)
            rl.addWidget(text, 1)
            if opt.tip:
                chk.setToolTip(opt.tip)
                text.setToolTip(opt.tip)
            grid.addWidget(row, r, 0, 1, 2)
            self.option_widgets[opt.label] = chk
            return r + 1
        if opt.kind == "checks":
            grid.addWidget(label, r, 0, 1, 2)
            r += 1
            box = QWidget()
            bl = QGridLayout(box)
            bl.setContentsMargins(0, 0, 0, 0)
            box.setProperty("checks", [])
            boxes = []
            for i, choice in enumerate(opt.choices):
                chk = QCheckBox(choice)
                chk.setChecked(choice in (opt.default or []))
                bl.addWidget(chk, i // 2, i % 2)
                boxes.append(chk)
            box.checkboxes = boxes
            grid.addWidget(box, r, 0, 1, 2)
            self.option_widgets[opt.label] = box
            return r + 1
        if opt.kind == "combo":
            w = QComboBox()
            # never let a long choice widen the panel; the drop-down list shows it in full
            w.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            w.setMinimumContentsLength(12)
            w.addItems(opt.choices)
            w.view().setMinimumWidth(w.view().sizeHintForColumn(0) + 24)
            if opt.default in opt.choices:
                w.setCurrentText(opt.default)
        elif opt.kind == "spin":
            w = QSpinBox()
            w.setRange(1, 9999)
            w.setValue(int(opt.default or 1))
        elif opt.kind == "lines":
            w = QPlainTextEdit()
            w.setPlaceholderText(opt.placeholder)
            w.setFixedHeight(96)
        else:
            w = QLineEdit()
            w.setPlaceholderText(opt.placeholder)
            if opt.default:
                w.setText(str(opt.default))
            if opt.kind == "password":
                w.setEchoMode(QLineEdit.EchoMode.Password)
        if opt.tip:
            w.setToolTip(opt.tip)
        grid.addWidget(label, r, 0, 1, 2)
        grid.addWidget(w, r + 1, 0, 1, 2)
        self.option_widgets[opt.label] = w
        w.setProperty("field_label", label)
        return r + 2

    def _wire_dependencies(self) -> None:
        """Enable an option only while the combo it depends on shows a matching choice."""
        for opt in self.tool.options:
            if not opt.enabled_when:
                continue
            target = self.option_widgets.get(opt.label)
            source = self.option_widgets.get(opt.enabled_when[0])
            if not isinstance(source, QComboBox) or target is None:
                continue
            allowed = opt.enabled_when[1]

            def update(_=None, t=target, s=source, ok=allowed):
                on = s.currentText() in ok
                t.setEnabled(on)
                lbl = t.property("field_label")
                if lbl is not None:
                    lbl.setEnabled(on)
            source.currentTextChanged.connect(update)
            update()

    def values(self) -> dict:
        """Current option values keyed by the option label shown on screen."""
        out = {}
        for label, w in self.option_widgets.items():
            if isinstance(w, QCheckBox):
                out[label] = w.isChecked()
            elif isinstance(w, QComboBox):
                out[label] = w.currentText()
            elif isinstance(w, QSpinBox):
                out[label] = w.value()
            elif isinstance(w, QLineEdit):
                out[label] = w.text() if w.isEnabled() else ""
            elif isinstance(w, QPlainTextEdit):
                out[label] = [t.strip() for t in w.toPlainText().splitlines() if t.strip()]
            elif hasattr(w, "checkboxes"):
                out[label] = [c.text() for c in w.checkboxes if c.isChecked()]
        return out

    # ------------------------------------------------------------ files

    def _add_files(self) -> None:
        if self.tool.multi:
            files, _ = QFileDialog.getOpenFileNames(self, "Add files", "", FILTERS[self.tool.accepts])
        else:
            one, _ = QFileDialog.getOpenFileName(self, "Add file", "", FILTERS[self.tool.accepts])
            files = [one] if one else []
            if files:
                self.files.clear_all()
        self.files.add_paths([Path(f) for f in files])

    def _add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Add a folder")
        if folder:
            self.files.add_paths([Path(folder)])

    def _browse_out(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Save results to")
        if folder:
            self.out.setText(folder)

    def _files_changed(self) -> None:
        n = self.files.rowCount()
        if not self.tool.multi and n > 1:
            keep = self.files.paths[-1]
            self.files.blockSignals(True)
            self.files.clear_all()
            self.files.add_paths([keep])
            self.files.blockSignals(False)
            n = 1
        self.count.setText(f"{n} file(s)" if n else "")
        if self.tool.workspace:
            self.selected.setText(f"Selected: {self.files.paths[0].name}" if n else
                                  "No file selected - add a PDF or drop it on the page area.")
            if self.pages_ws is not None:
                self._load_workspace()
        self.run_btn.setEnabled(n > 0 and not self._busy())
        self.status.setText("Ready." if n else "Add files to begin.")

    def _load_workspace(self) -> None:
        if not self.files.paths:
            self.pages_ws.clear()
            return
        path = self.files.paths[0]
        if not self._ask_passwords([str(path)]):
            self.files.clear_all()
            return
        try:
            self.pages_ws.load(path, self.passwords.get(str(path), ""))
        except Exception as exc:
            QMessageBox.warning(self, self.tool.name, f"'{path.name}' could not be opened:\n{exc}")
            self.files.clear_all()

    def _ws_changed(self) -> None:
        if self.pages_ws is not None and self.pages_ws.path:
            self.status.setText(self.pages_ws.summary())

    # ------------------------------------------------------------ running

    def _busy(self) -> bool:
        return self.runner is not None and self.runner.busy

    def _ask_passwords(self, files: list[str]) -> bool:
        """Ask once per protected PDF (3 tries). Passwords stay in memory for this session."""
        if self.tool.accepts != "pdf" or self.tool.id == "unprotect":
            return True
        from .services.common import check_password, is_encrypted
        for f in files:
            if not is_encrypted(f) or check_password(f, self.passwords.get(f, "")):
                continue
            for attempt in range(3):
                pw, ok = QInputDialog.getText(
                    self, "Password needed",
                    f"'{Path(f).name}' is password-protected.\nEnter its password"
                    + (" (incorrect - try again)" if attempt else "") + ":", QLineEdit.EchoMode.Password)
                if not ok:
                    return False
                if check_password(f, pw):
                    self.passwords[f] = pw
                    break
            else:
                QMessageBox.warning(self, "Password", f"The password for '{Path(f).name}' was not accepted.")
                return False
        return True

    def _unprotect_passwords(self, files: list[str]) -> bool:
        """Remove PDF Password: use the typed password, or ask per file if it does not fit."""
        from .services.common import check_password
        typed = self.values().get("Current password", "")
        for f in files:
            if typed and check_password(f, typed):
                self.passwords[f] = typed
                continue
            pw, ok = QInputDialog.getText(self, "Current password",
                                          f"Enter the current password of '{Path(f).name}':",
                                          QLineEdit.EchoMode.Password)
            if not ok:
                return False
            self.passwords[f] = pw
        return True

    def _run(self, _=False, extra: dict | None = None) -> None:
        if not self.tool.ready:
            QMessageBox.information(self, self.tool.name,
                                    f"'{self.tool.name}' is not connected yet.\n\nThe screens are ready; the "
                                    "processing engine for this tool is added in a later build stage.")
            return
        from .runners import RUNNERS, is_heavy
        files = [str(p) for p in self.files.paths]
        if not files:
            return
        if self.tool.id == "unprotect":
            if not self._unprotect_passwords(files):
                return
        elif not self._ask_passwords(files):
            return
        out_dir = self.out.text().strip()
        if out_dir and not os.path.isdir(out_dir):
            QMessageBox.warning(self, self.tool.name, f"The output folder does not exist:\n{out_dir}")
            return
        opts = self.values()
        if self.pages_ws is not None:
            opts["_order"] = self.pages_ws.order()
        if extra:
            opts.update(extra)
        from .jobs import JobRunner
        if self.runner is None:
            self.runner = JobRunner(self)
            self.runner.progressed.connect(self._on_progress)
            self.runner.finished.connect(self._on_finished)
        self._last_request = (files, opts, out_dir)
        self.result.setVisible(False)
        self.run_btn.setEnabled(False)
        self.progress.setRange(0, 0)
        self.progress.setVisible(True)
        self.cancel_btn.setVisible(True)
        self.cancel_btn.setEnabled(True)
        self.status.setText("Working…")
        self.runner.start(RUNNERS[self.tool.id], {"files": files, "opts": opts, "out_dir": out_dir,
                                                  "passwords": dict(self.passwords)},
                          heavy=is_heavy(self.tool.id, opts))

    def _cancel(self) -> None:
        if self.runner is not None:
            self.runner.cancel()
            self.cancel_btn.setEnabled(False)
            self.status.setText("Cancelling…")

    def _on_progress(self, done: int, total: int, text: str) -> None:
        if total > 0:
            self.progress.setRange(0, total)
            self.progress.setValue(min(done, total))
        if text:
            self.status.setText(text)

    def _on_finished(self, status: str, payload) -> None:
        self.progress.setVisible(False)
        self.cancel_btn.setVisible(False)
        self.run_btn.setEnabled(bool(self.files.paths))
        if status == "cancelled":
            self.status.setText("Cancelled - nothing was saved for the file in progress.")
            return
        if status == "error":
            self.status.setText("Stopped - see the message.")
            self._show_result(False, "Could not complete", str(payload), [])
            return
        res = payload or {}
        if res.get("confirm"):
            conf = res["confirm"]
            dlg = ConfirmDialog(self, conf.get("title", self.tool.name), conf["lines"], self.tool.action)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                self._run(extra={"_plan": conf["plans"]})
            else:
                self.status.setText("Nothing was changed.")
            return
        files = res.get("files", [])
        self.last_files = files
        lines = [res.get("message", "")] + res.get("details", [])
        warnings = res.get("warnings", [])
        if warnings:
            lines.append("")
            lines += [f"⚠ {w}" for w in warnings]
        if files:
            lines.append("")
            shown = files[:8]
            lines += [f"•  {Path(f).name}" for f in shown]
            if len(files) > len(shown):
                lines.append(f"…and {len(files) - len(shown)} more")
        self.status.setText(res.get("message", "Done."))
        self._show_result(True, "Done" if not warnings else "Done - please read the notes", "\n".join(lines),
                          files)

    def _show_result(self, ok: bool, title: str, text: str, files: list[str]) -> None:
        colour = theme.SUCCESS if ok else theme.ERROR
        self.result_icon.setPixmap(pixmap("check-square" if ok else "info", colour, 20))
        self.result_title.setText(title)
        self.result_text.setText(text)
        self.open_btn.setVisible(bool(files))
        self.result.setVisible(True)

    def prefill(self, files: list[str], values: dict) -> None:
        """Open this tool with files and option values (e.g. Verify after a redaction)."""
        self.files.clear_all()
        self.files.add_paths([Path(f) for f in files])
        for label, value in values.items():
            w = self.option_widgets.get(label)
            if isinstance(w, QPlainTextEdit):
                w.setPlainText("\n".join(value))
            elif isinstance(w, QLineEdit):
                w.setText(str(value))

    def _open_folder(self) -> None:
        if self.last_files:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(self.last_files[0]).parent)))
