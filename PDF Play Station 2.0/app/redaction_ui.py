"""Secure Redaction workspace.

Manual Redaction, Find & Redact, Smart Redaction, Review and Apply are five views of
ONE redaction session: the same open PDF and the same list of marked areas. The
sidebar entries switch the panel on the right; the page viewer stays.

Ported from the earlier PDF Play Station (v1.1.0) to PySide6. New: OCR options for
scanned pages, 13 Smart categories, solid-black / OCR verification in the summary,
and a direct hand-over to Verify Redacted PDF.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import pymupdf
from PySide6.QtCore import QPointF, QRectF, Qt, QUrl, Signal
from PySide6.QtGui import (QBrush, QColor, QDesktopServices, QFontMetrics, QImage, QIntValidator, QKeySequence,
                           QPainter, QPen, QPixmap, QShortcut)
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame,
                               QGraphicsScene, QGraphicsTextItem, QGraphicsView, QGridLayout, QHBoxLayout,
                               QHeaderView, QInputDialog, QLabel, QLineEdit, QMenu, QMessageBox, QPlainTextEdit,
                               QProgressBar, QPushButton, QScrollArea, QSplitter, QStackedWidget, QToolButton,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from . import theme
from .catalog import ALL_TOOLS, OCR_LANG, SMART_CATEGORIES
from .icons import icon, pixmap
from .services.ocr import LANGUAGE_CHOICES

MODES = ["manual", "find", "smart", "review", "apply"]
MODE_TITLES = {"manual": "Mark", "find": "Find", "smart": "Smart detect", "review": "Review", "apply": "Apply"}
ZOOM_LEVELS = [0.25, 0.33, 0.5, 0.67, 0.75, 0.9, 1.0, 1.1, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 4.0]
SCREEN = 96.0 / 72.0
OCR_MODES = ["Automatic (recommended)", "Always run OCR", "Off"]
STATUS_COLOURS = {"PASS": theme.SUCCESS, "ABSENT": theme.SUCCESS, "FAIL": theme.ERROR, "FOUND": theme.ERROR,
                  "WARN": theme.WARNING, "INFO": theme.WORD, "NOT CHECKED": theme.MUTED}


def mask_value(text: str) -> str:
    from .services.redaction import mask_value as mv
    return mv(text)


def _label(text: str, role: str = "", obj: str = "", wrap: bool = True) -> QLabel:
    lbl = QLabel(text)
    if role:
        lbl.setProperty("role", role)
    if obj:
        lbl.setObjectName(obj)
    lbl.setWordWrap(wrap)
    return lbl


def _btn(text: str, slot, obj: str = "", tip: str = "", ic: str = "") -> QPushButton:
    b = QPushButton(icon(ic), text) if ic else QPushButton(text)
    if obj:
        b.setObjectName(obj)
    if tip:
        b.setToolTip(tip)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.clicked.connect(slot)
    return b


def _notice(text: str) -> QFrame:
    note = QFrame()
    note.setObjectName("notice")
    nl = QHBoxLayout(note)
    nl.setContentsMargins(10, 8, 10, 8)
    ic = QLabel()
    ic.setPixmap(pixmap("info", theme.WARNING, 16))
    nl.addWidget(ic, 0, Qt.AlignmentFlag.AlignTop)
    nl.addWidget(_label(text), 1)
    return note


def fill_report(tree: QTreeWidget, checks) -> None:
    tree.clear()
    for status, check, detail in checks:
        item = QTreeWidgetItem([status, check, detail])
        item.setForeground(0, QBrush(QColor(STATUS_COLOURS.get(status, theme.TEXT))))
        f = item.font(0)
        f.setBold(True)
        item.setFont(0, f)
        item.setToolTip(2, detail)
        tree.addTopLevelItem(item)
    tree.resizeColumnToContents(0)
    tree.resizeColumnToContents(1)


# ================================================================== session

class Mark:
    """A pending redaction region (unrotated PDF page coordinates)."""
    _next = 1

    def __init__(self, page: int, rect: tuple, source: str, label: str, text: Optional[str] = None,
                 approved: bool = True):
        self.id = Mark._next
        Mark._next += 1
        self.page, self.rect, self.source, self.label = page, tuple(rect), source, label
        self.text, self.approved = text, approved

    def key(self) -> tuple:
        return rect_key(self.page, self.rect)


def rect_key(page: int, rect) -> tuple:
    return (page,) + tuple(int(round(v * 2)) for v in rect)


class RedactionController:
    """Pending marks plus an undo history. All edits go through here."""

    def __init__(self):
        self.marks: list[Mark] = []
        self.history: list[tuple] = []
        self.last_terms: list[str] = []
        self.last_output: str = ""

    def reset(self):
        self.marks, self.history = [], []

    def keys(self) -> set:
        return {m.key() for m in self.marks}

    def add(self, specs: list[tuple]) -> int:
        keys, new = self.keys(), []
        for page, rect, source, label, text in specs:
            k = rect_key(page, rect)
            if k not in keys:
                keys.add(k)
                new.append(Mark(page, rect, source, label, text))
        if new:
            self.marks.extend(new)
            self.history.append(("add", new))
        return len(new)

    def remove(self, marks: list[Mark]) -> int:
        ids = {m.id for m in marks}
        removed = [m for m in self.marks if m.id in ids]
        if removed:
            self.marks = [m for m in self.marks if m.id not in ids]
            self.history.append(("remove", removed))
        return len(removed)

    def modify(self, mark_id: int, rect: tuple) -> None:
        m = self.get(mark_id)
        if m and tuple(rect) != m.rect:
            self.history.append(("modify", m.id, m.rect))
            m.rect = tuple(rect)

    def set_approved(self, marks: list[Mark], value: bool) -> None:
        changed = [(m.id, m.approved) for m in marks if m.approved != value]
        if changed:
            for m in marks:
                m.approved = value
            self.history.append(("approve", changed))

    def get(self, mark_id: int) -> Optional[Mark]:
        return next((m for m in self.marks if m.id == mark_id), None)

    def undo(self) -> str:
        if not self.history:
            return "Nothing to undo."
        action = self.history.pop()
        if action[0] == "add":
            ids = {m.id for m in action[1]}
            self.marks = [m for m in self.marks if m.id not in ids]
            return f"Undone: {len(ids)} region(s) added."
        if action[0] == "remove":
            self.marks.extend(action[1])
            return f"Undone: {len(action[1])} region(s) removed."
        if action[0] == "modify":
            m = self.get(action[1])
            if m:
                m.rect = action[2]
            return "Undone: region moved/resized."
        for mid, old in action[1]:
            m = self.get(mid)
            if m:
                m.approved = old
        return "Undone: approval change."


# ================================================================== viewer

class PDFViewerWidget(QGraphicsView):
    """Single-page viewer. Drag on empty space to draw a region; drag a region to
    move it; drag its bottom-right corner to resize; Delete removes the selected one."""
    rectDrawn = Signal(QRectF)
    markChanged = Signal(int, QRectF)
    markDeleted = Signal(int)
    zoomStep = Signal(int)
    fileDropped = Signal(str)

    HANDLE = 9

    def __init__(self):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.setBackgroundBrush(QColor("#E9ECF1"))
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.page_item = None
        self.overlays: list = []
        self.selected_id: Optional[int] = None
        self._mode = None
        self._origin = None
        self._item = None
        self._start_rect = None
        self.show_empty()

    def show_empty(self):
        self.scene().clear()
        self.page_item, self.overlays, self._mode, self._item = None, [], None, None
        t = QGraphicsTextItem()
        t.setHtml(f"<div style='text-align:center;color:{theme.NAVY};font-size:14pt'><b>Open a PDF to start "
                  "redacting</b><br><span style='font-size:10pt;color:#4A5568'>Use 'Open PDF' or drag and drop a "
                  "PDF here. Then drag on the page to mark an area, or use Find / Smart detect.</span></div>")
        t.setTextWidth(460)
        self.scene().addItem(t)
        self.scene().setSceneRect(t.boundingRect())
        self.viewport().setCursor(Qt.CursorShape.ArrowCursor)

    def set_page(self, pm: QPixmap, w: float, h: float):
        self.scene().clear()
        self.overlays, self._mode, self._item = [], None, None
        self.scene().addRect(QRectF(4, 4, w, h), QPen(Qt.PenStyle.NoPen), QBrush(QColor(11, 30, 61, 50)))
        self.page_item = self.scene().addPixmap(pm)
        actual = self.page_item.boundingRect().width()
        if actual > 0 and abs(actual - w) > 1:
            self.page_item.setScale(w / actual)
        self.scene().setSceneRect(QRectF(-24, -24, w + 48, h + 48))

    def set_overlays(self, items):
        for it in self.overlays:
            self.scene().removeItem(it)
        self.overlays = []
        styles = {
            "approved": (QPen(QColor(theme.ERROR), 1.6), QBrush(QColor(180, 35, 24, 80)), 5),
            "excluded": (QPen(QColor(theme.MUTED), 1.4, Qt.PenStyle.DashLine), QBrush(QColor(138, 143, 153, 40)), 5),
            "candidate": (QPen(QColor(theme.WORD), 1.3, Qt.PenStyle.DashLine), QBrush(QColor(30, 78, 140, 30)), 4),
            "focus": (QPen(QColor(theme.GOLD), 2.8), QBrush(Qt.BrushStyle.NoBrush), 6),
        }
        for rect, kind, mid in items:
            pen, brush, z = styles[kind]
            if kind in ("approved", "excluded") and mid == self.selected_id:
                pen = QPen(QColor(theme.GOLD), 2.4)
            it = self.scene().addRect(rect, pen, brush)
            it.setZValue(z)
            it.setData(0, kind)
            it.setData(1, mid)
            if kind in ("approved", "excluded"):
                it.setToolTip("Pending redaction" + ("" if kind == "approved" else " (excluded in review)")
                              + " - drag to move, drag the corner to resize, Delete or right-click to remove")
            self.overlays.append(it)

    def _mark_at(self, pos):
        for it in self.items(pos):
            if it.data(0) in ("approved", "excluded"):
                return it
        return None

    def _clamp(self, p: QPointF) -> QPointF:
        r = self.page_item.sceneBoundingRect()
        return QPointF(min(max(p.x(), r.left()), r.right()), min(max(p.y(), r.top()), r.bottom()))

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.page_item is not None:
            scene_pos = self.mapToScene(e.position().toPoint())
            item = self._mark_at(e.position().toPoint())
            if item is not None:
                self.selected_id = int(item.data(1))
                self._item, self._origin, self._start_rect = item, scene_pos, QRectF(item.rect())
                br = item.rect().bottomRight()
                self._mode = ("resize" if abs(scene_pos.x() - br.x()) <= self.HANDLE and
                              abs(scene_pos.y() - br.y()) <= self.HANDLE else "move")
                item.setPen(QPen(QColor(theme.GOLD), 2.4))
                self.setFocus()
                return
            if self.page_item.sceneBoundingRect().contains(scene_pos):
                self.selected_id = None
                self._mode, self._origin = "draw", scene_pos
                self._item = self.scene().addRect(QRectF(scene_pos, scene_pos),
                                                  QPen(QColor(theme.ERROR), 1.5, Qt.PenStyle.DashLine),
                                                  QBrush(QColor(180, 35, 24, 45)))
                self._item.setZValue(10)
                return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        pos = e.position().toPoint()
        if self._mode and self._item is not None:
            p = self._clamp(self.mapToScene(pos))
            if self._mode == "draw":
                self._item.setRect(QRectF(self._origin, p).normalized())
            elif self._mode == "move":
                r = QRectF(self._start_rect)
                r.translate(p - self._origin)
                bounds = self.page_item.sceneBoundingRect()
                r.moveLeft(min(max(r.left(), bounds.left()), bounds.right() - r.width()))
                r.moveTop(min(max(r.top(), bounds.top()), bounds.bottom() - r.height()))
                self._item.setRect(r)
            else:
                self._item.setRect(QRectF(self._start_rect.topLeft(), p).normalized())
            return
        if self.page_item is not None:
            item = self._mark_at(pos)
            if item is not None:
                sp = self.mapToScene(pos)
                br = item.rect().bottomRight()
                near = abs(sp.x() - br.x()) <= self.HANDLE and abs(sp.y() - br.y()) <= self.HANDLE
                self.viewport().setCursor(Qt.CursorShape.SizeFDiagCursor if near else Qt.CursorShape.SizeAllCursor)
            else:
                self.viewport().setCursor(Qt.CursorShape.CrossCursor)
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self._mode and e.button() == Qt.MouseButton.LeftButton:
            mode, item = self._mode, self._item
            self._mode, self._item = None, None
            rect = item.rect()
            if mode == "draw":
                self.scene().removeItem(item)
                if rect.width() >= 3 and rect.height() >= 3:
                    self.rectDrawn.emit(rect)
            elif rect != self._start_rect and rect.width() >= 3 and rect.height() >= 3:
                self.markChanged.emit(int(item.data(1)), rect)
            else:
                self.markChanged.emit(int(item.data(1)), QRectF())      # selection only -> refresh
            return
        super().mouseReleaseEvent(e)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and self.selected_id is not None:
            self.markDeleted.emit(self.selected_id)
            self.selected_id = None
            return
        super().keyPressEvent(e)

    def contextMenuEvent(self, e):
        item = self._mark_at(e.pos())
        if item is not None:
            menu = QMenu(self)
            act = menu.addAction("Remove this pending redaction")
            if menu.exec(e.globalPos()) is act:
                self.markDeleted.emit(int(item.data(1)))

    def wheelEvent(self, e):
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoomStep.emit(1 if e.angleDelta().y() > 0 else -1)
            e.accept()
        else:
            super().wheelEvent(e)

    def _pdfs(self, mime) -> list[str]:
        return [u.toLocalFile() for u in mime.urls() if u.isLocalFile() and u.toLocalFile().lower().endswith(".pdf")]

    def dragEnterEvent(self, e):
        e.acceptProposedAction() if self._pdfs(e.mimeData()) else e.ignore()

    def dragMoveEvent(self, e):
        self.dragEnterEvent(e)

    def dropEvent(self, e):
        files = self._pdfs(e.mimeData())
        if files:
            e.acceptProposedAction()
            self.fileDropped.emit(files[0])


# ================================================================== summary dialog

class RedactionSummaryDialog(QDialog):
    def __init__(self, parent: QWidget, r: dict, on_verify):
        super().__init__(parent)
        self.out = r["out"]
        self.setWindowTitle("Redaction summary")
        self.resize(860, 580)
        lay = QVBoxLayout(self)
        head = _label("Verification passed - the redacted PDF is saved." if not r["failed"] else
                      "VERIFICATION FAILED - do not share this file. Review the failed checks below.",
                      role="ok" if not r["failed"] else "error")
        f = head.font()
        f.setPointSizeF(12)
        f.setBold(True)
        head.setFont(f)
        lay.addWidget(head)
        lines = [f"Output: {r['out']}",
                 f"Pages redacted: {r['pages_processed']}   |   Areas removed: {r['regions']}"]
        if r["flattened"]:
            lines.append("Flattened pages (text there is no longer searchable): " +
                         "; ".join(f"p.{p} - {why}" for p, why in r["flattened"]))
        if r["toc_changed"]:
            lines.append(f"Bookmarks renamed to [REDACTED]: {r['toc_changed']}")
        lines += ["Clean-up: " + n for n in r["notes"]]
        if r["was_encrypted"]:
            lines.append("Note: the source was password-protected; the redacted copy is saved without a password.")
        info = _label("\n".join(lines))
        info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(info)
        tree = QTreeWidget()
        tree.setHeaderLabels(["Status", "Check", "Detail"])
        tree.setRootIsDecorated(False)
        tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        fill_report(tree, r["checks"])
        lay.addWidget(tree, 1)
        lay.addWidget(_label("Automated checks cannot prove resistance to every forensic technique; look through "
                             "the output before sharing it.", role="hint"))
        row = QHBoxLayout()
        b1 = QPushButton(icon("doc"), "Open redacted PDF")
        b1.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.out)))
        b2 = QPushButton(icon("folder-open"), "Open folder")
        b2.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(self.out))))
        b3 = QPushButton(icon("verify"), "Verify in detail…")
        b3.setToolTip("Open Verify Redacted PDF with this file and the redacted values")
        b3.clicked.connect(lambda: (self.accept(), on_verify()))
        close = QPushButton("Close")
        close.setObjectName("primary")
        close.clicked.connect(self.accept)
        for b in (b1, b2, b3):
            row.addWidget(b)
        row.addStretch(1)
        row.addWidget(close)
        lay.addLayout(row)


# ================================================================== workspace page

class RedactionPage(QWidget):
    """The shared page for the five redaction tools."""
    mode_changed = Signal(str)                 # tells the main window which sidebar entry to highlight
    verify_requested = Signal(str, list)       # (output path, values) -> Verify Redacted PDF

    def __init__(self):
        super().__init__()
        self.ctl = RedactionController()
        self.doc: Optional[pymupdf.Document] = None
        self.path = ""
        self.password = ""
        self.cur = 0
        self.zoom = 1.0
        self.find_results: list[dict] = []
        self.smart_results: list[dict] = []
        self.ocr_cache: dict = {}
        self.focus: Optional[tuple] = None
        self.unsaved = False
        self.mode = "manual"
        self.runner = None
        self._on_done = None

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 20, 28, 16)
        root.setSpacing(10)
        crumbs = QHBoxLayout()
        crumbs.addWidget(_label("SECURE REDACTION", obj="pageBreadcrumb", wrap=False))
        crumbs.addStretch()
        root.addLayout(crumbs)
        title_row = QHBoxLayout()
        self.title_icon = QLabel()
        title_row.addWidget(self.title_icon)
        self.title = _label("", obj="pageTitle", wrap=False)
        title_row.addWidget(self.title)
        title_row.addStretch()
        root.addLayout(title_row)
        self.desc = _label("", obj="pageDescription")
        root.addWidget(self.desc)

        # mode switcher: the five tools are steps of one session
        steps = QHBoxLayout()
        steps.setSpacing(6)
        self.mode_group = QButtonGroup(self)
        self.mode_buttons: dict[str, QToolButton] = {}
        for i, m in enumerate(MODES):
            b = QToolButton()
            b.setObjectName("modeButton")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            b.setIcon(icon(ALL_TOOLS[m][1].icon, theme.ERROR))
            b.clicked.connect(lambda _=False, mm=m: self.set_mode(mm, user=True))
            self.mode_group.addButton(b)
            self.mode_buttons[m] = b
            steps.addWidget(b)
            if i < len(MODES) - 1:
                arrow = QLabel()
                arrow.setPixmap(pixmap("chevron-right", theme.BORDER_STRONG, 14))
                steps.addWidget(arrow)
        steps.addStretch()
        root.addLayout(steps)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(self._viewer_card())
        self.panels = QStackedWidget()
        self.panel_index: dict[str, int] = {}
        for m, builder in (("manual", self._panel_manual), ("find", self._panel_find), ("smart", self._panel_smart),
                           ("review", self._panel_review), ("apply", self._panel_apply)):
            self.panel_index[m] = self.panels.addWidget(self._scroll(builder()))
        side = QFrame()
        side.setProperty("card", True)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(14, 12, 14, 12)
        sl.addWidget(self.panels)
        side.setMinimumWidth(400)
        split.addWidget(side)
        split.setStretchFactor(0, 1)
        split.setSizes([760, 440])
        split.setChildrenCollapsible(False)
        root.addWidget(split, 1)

        bar = QFrame()
        bar.setProperty("card", True)
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(16, 8, 16, 8)
        self.status = _label("Open a PDF to begin.", role="hint", wrap=False)
        bl.addWidget(self.status, 1)
        self.progress = QProgressBar()
        self.progress.setFixedWidth(240)
        self.progress.setVisible(False)
        bl.addWidget(self.progress)
        self.cancel_btn = _btn("Cancel", self._cancel, ic="clear")
        self.cancel_btn.setVisible(False)
        bl.addWidget(self.cancel_btn)
        root.addWidget(bar)

        for seq, slot in (("PgUp", self.prev_page), ("PgDown", self.next_page), ("Ctrl+Z", self.undo),
                          ("Ctrl++", lambda: self.zoom_step(1)), ("Ctrl+=", lambda: self.zoom_step(1)),
                          ("Ctrl+-", lambda: self.zoom_step(-1))):
            sc = QShortcut(QKeySequence(seq), self)
            sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(slot)
        self.set_mode("manual")
        self.refresh()

    # ------------------------------------------------------------ building

    @staticmethod
    def _scroll(content: QWidget) -> QScrollArea:
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        area.setWidget(content)
        return area

    def _viewer_card(self) -> QFrame:
        card = QFrame()
        card.setProperty("card", True)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)
        bar = QHBoxLayout()
        bar.setSpacing(5)
        self.b_open = _btn("Open PDF", lambda: self.open_pdf(), ic="file-plus")
        self.b_prev = _btn("‹", self.prev_page, tip="Previous page (Page Up)")
        self.page_edit = QLineEdit()
        self.page_edit.setFixedWidth(QFontMetrics(self.page_edit.font()).horizontalAdvance("99999") + 22)
        self.page_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_edit.setValidator(QIntValidator(1, 999999))
        self.page_edit.returnPressed.connect(self.jump)
        self.page_total = _label("/0", wrap=False)
        self.b_next = _btn("›", self.next_page, tip="Next page (Page Down)")
        self.b_zout = _btn("−", lambda: self.zoom_step(-1), tip="Zoom out (Ctrl+-)")
        self.zoom_lbl = _label("100%", wrap=False)
        self.zoom_lbl.setMinimumWidth(44)
        self.zoom_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.b_zin = _btn("+", lambda: self.zoom_step(1), tip="Zoom in (Ctrl++)")
        self.b_fitw = _btn("Fit width", self.fit_width)
        self.b_undo = _btn("Undo", self.undo, tip="Undo the last change (Ctrl+Z)")
        for w in (self.b_open, self.b_prev, self.page_edit, self.page_total, self.b_next, self.b_zout,
                  self.zoom_lbl, self.b_zin, self.b_fitw):
            bar.addWidget(w)
        bar.addStretch()
        bar.addWidget(self.b_undo)
        lay.addLayout(bar)
        self.banner = _label("", role="ok")
        self.banner.setVisible(False)
        lay.addWidget(self.banner)
        self.view = PDFViewerWidget()
        self.view.rectDrawn.connect(self.on_rect_drawn)
        self.view.markChanged.connect(self.on_mark_changed)
        self.view.markDeleted.connect(lambda mid: self.remove_marks([self.ctl.get(mid)]))
        self.view.zoomStep.connect(self.zoom_step)
        self.view.fileDropped.connect(self.open_pdf)
        lay.addWidget(self.view, 1)
        legend = QHBoxLayout()
        for colour, text in ((theme.ERROR, "Marked for redaction"), (theme.MUTED, "Excluded in review"),
                             (theme.WORD, "Found / detected - not yet added")):
            sw = QLabel()
            sw.setFixedSize(14, 10)
            sw.setStyleSheet(f"background:{colour}; border-radius:2px;")
            legend.addWidget(sw)
            legend.addWidget(_label(text, role="hint", wrap=False))
            legend.addSpacing(10)
        legend.addStretch()
        lay.addLayout(legend)
        return card

    def _tree(self, headers: list[str]) -> QTreeWidget:
        tree = QTreeWidget()
        tree.setMinimumHeight(QFontMetrics(tree.font()).height() * 10)
        tree.setHeaderLabels(headers)
        tree.setRootIsDecorated(False)
        tree.setUniformRowHeights(True)
        tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        tree.header().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        tree.header().setStretchLastSection(True)
        return tree

    def _ocr_row(self, lay: QVBoxLayout) -> tuple[QComboBox, QComboBox]:
        grid = QGridLayout()
        grid.addWidget(_label("Scanned pages", role="field", wrap=False), 0, 0)
        mode = QComboBox()
        mode.addItems(OCR_MODES)
        mode.setToolTip("Automatic: pages without a text layer are read with OCR")
        grid.addWidget(mode, 0, 1)
        grid.addWidget(_label("OCR language", role="field", wrap=False), 1, 0)
        lang = QComboBox()
        lang.addItems(OCR_LANG.choices)
        lang.setCurrentText(OCR_LANG.default)
        grid.addWidget(lang, 1, 1)
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)
        return mode, lang

    def _panel_manual(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 4, 0)
        lay.addWidget(_label("How to mark areas", role="cardTitle"))
        lay.addWidget(_label(
            "1.  Open a PDF and go to the page.\n"
            "2.  Drag on the page to draw a box over anything that must be removed.\n"
            "3.  Drag a box to move it; drag its bottom-right corner to resize it.\n"
            "4.  Select a box and press Delete (or right-click) to remove it.\n"
            "5.  Boxes are kept while you move between pages. Check them in Review, then Apply."))
        row = QHBoxLayout()
        row.addWidget(_btn("Add a box here", self.add_default_box, tip="Places a box in the middle of the view"))
        row.addWidget(_btn("Clear this page", self.clear_page))
        row.addWidget(_btn("Clear all", self.clear_all))
        lay.addLayout(row)
        self.manual_count = _label("", role="hint")
        lay.addWidget(self.manual_count)
        lay.addWidget(_notice("Anything inside a box is removed for good in the new file: text, images and "
                              "drawings. The original PDF is never changed."))
        lay.addStretch()
        return w

    def _panel_find(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 4, 0)
        lay.addWidget(_label("Search for", role="field"))
        self.find_edit = QPlainTextEdit()
        self.find_edit.setPlaceholderText("One term per line - a name, PAN, account number, reference…")
        self.find_edit.setMaximumHeight(80)
        lay.addWidget(self.find_edit)
        opts = QGridLayout()
        self.f_case = QCheckBox("Match case")
        self.f_word = QCheckBox("Whole words only")
        self.f_word.setChecked(True)
        self.f_space = QCheckBox("Ignore spaces / hyphens")
        self.f_space.setChecked(True)
        self.f_space.setToolTip("'1234 5678' also finds '12345678' and '1234-5678'")
        for i, cb in enumerate((self.f_case, self.f_word, self.f_space)):
            opts.addWidget(cb, i // 2, i % 2)
        lay.addLayout(opts)
        self.f_ocr, self.f_lang = self._ocr_row(lay)
        lay.addWidget(_btn("Find all", self.run_find, obj="primary", ic="search"))
        self.find_tree = self._tree(["", "Page", "Match", "Context"])
        self.find_tree.currentItemChanged.connect(lambda cur, _p: self.on_candidate(cur, self.find_results))
        lay.addWidget(self.find_tree, 1)
        row = QHBoxLayout()
        row.addWidget(_btn("Tick all", lambda: self.tick(self.find_tree, True)))
        row.addWidget(_btn("Untick all", lambda: self.tick(self.find_tree, False)))
        self.f_show = QCheckBox("Show values")
        self.f_show.toggled.connect(lambda _on: self.fill_find())
        row.addWidget(self.f_show)
        lay.addLayout(row)
        self.find_count = _label("Matches are listed for review; nothing is redacted automatically.", role="hint")
        lay.addWidget(self.find_count)
        lay.addWidget(_btn("Add ticked matches to the redaction list", self.add_found, obj="danger"))
        return w

    def _panel_smart(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 4, 0)
        lay.addWidget(_label("Detect", role="field"))
        grid = QGridLayout()
        self.cat_boxes: dict[str, QCheckBox] = {}
        default = ALL_TOOLS["smart"][1].options[0].default
        for i, cat in enumerate(SMART_CATEGORIES):
            cb = QCheckBox(cat)
            cb.setChecked(cat in default)
            self.cat_boxes[cat] = cb
            grid.addWidget(cb, i // 2, i % 2)
        lay.addLayout(grid)
        self.s_pan_case = QCheckBox("PAN in any letter case")
        self.s_bank_kw = QCheckBox("Bank account: only with 'A/c No.' or similar nearby")
        self.s_bank_kw.setChecked(True)
        lay.addWidget(self.s_pan_case)
        lay.addWidget(self.s_bank_kw)
        self.s_ocr, self.s_lang = self._ocr_row(lay)
        lay.addWidget(_btn("Scan document", self.run_scan, obj="primary", ic="sparkles"))
        frow = QHBoxLayout()
        frow.addWidget(_label("Show", wrap=False))
        self.s_filter = QComboBox()
        self.s_filter.addItems(["All categories"] + SMART_CATEGORIES)
        self.s_filter.currentIndexChanged.connect(lambda _i: self.fill_smart())
        frow.addWidget(self.s_filter, 1)
        self.s_show = QCheckBox("Show values")
        self.s_show.toggled.connect(lambda _on: self.fill_smart())
        frow.addWidget(self.s_show)
        lay.addLayout(frow)
        self.smart_tree = self._tree(["", "Type", "Value", "Page", "Confidence", "Why"])
        self.smart_tree.currentItemChanged.connect(lambda cur, _p: self.on_candidate(cur, self.smart_results))
        self.smart_tree.itemChanged.connect(self._smart_ticked)
        lay.addWidget(self.smart_tree, 1)
        row = QHBoxLayout()
        row.addWidget(_btn("Tick all", lambda: self.tick(self.smart_tree, True)))
        row.addWidget(_btn("Untick all", lambda: self.tick(self.smart_tree, False)))
        row.addWidget(_btn("High only", self.tick_high, tip="Tick only High-confidence items"))
        lay.addLayout(row)
        self.smart_count = _label("Not scanned yet.", role="hint")
        lay.addWidget(self.smart_count)
        lay.addWidget(_btn("Add ticked items to the redaction list", self.add_smart, obj="danger"))
        lay.addWidget(_notice("Detection is pattern-based and offline (Aadhaar and GSTIN check digits are "
                              "verified). A match does not prove a number was issued, and zero matches do not "
                              "prove the document is free of personal data - names and addresses must be "
                              "marked by hand."))
        return w

    def _panel_review(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 4, 0)
        lay.addWidget(_label("Every marked area is listed. Untick a row to exclude it; only ticked areas are "
                             "removed. Click a row to see it on the page."))
        self.review_tree = self._tree(["", "Page", "Source", "Value / area"])
        self.review_tree.itemChanged.connect(self.on_review_tick)
        self.review_tree.currentItemChanged.connect(self.on_review_select)
        lay.addWidget(self.review_tree, 1)
        row = QHBoxLayout()
        row.addWidget(_btn("Approve all", lambda: self.approve_all(True)))
        row.addWidget(_btn("Exclude all", lambda: self.approve_all(False)))
        row.addWidget(_btn("Remove selected", self.remove_review_selected))
        lay.addLayout(row)
        self.r_show = QCheckBox("Show values")
        self.r_show.toggled.connect(lambda _on: self.refresh())
        lay.addWidget(self.r_show)
        self.review_count = _label("", role="hint")
        lay.addWidget(self.review_count)
        lay.addWidget(_btn("Continue to Apply  ›", lambda: self.set_mode("apply", user=True), obj="primary"))
        return w

    def _panel_apply(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 4, 0)
        self.apply_summary = _label("", role="field")
        lay.addWidget(self.apply_summary)
        grid = QGridLayout()
        grid.setColumnStretch(1, 1)
        grid.addWidget(_label("Save to folder", role="field", wrap=False), 0, 0)
        self.out_dir = QLineEdit()
        self.out_dir.setPlaceholderText("Same folder as the original")
        grid.addWidget(self.out_dir, 0, 1)
        grid.addWidget(_btn("Browse…", self._browse_out, ic="folder-open"), 0, 2)
        grid.addWidget(_label("File name", role="field", wrap=False), 1, 0)
        self.out_name = QLineEdit()
        grid.addWidget(self.out_name, 1, 1, 1, 2)
        grid.addWidget(_label("Patch resolution", role="field", wrap=False), 2, 0)
        self.dpi = QComboBox()
        self.dpi.addItems(["150 dpi", "200 dpi", "300 dpi", "400 dpi"])
        self.dpi.setCurrentText("300 dpi")
        self.dpi.setToolTip("Resolution of the image patches that replace redacted areas")
        grid.addWidget(self.dpi, 2, 1, 1, 2)
        grid.addWidget(_label("Drawings", role="field", wrap=False), 3, 0)
        self.vector = QComboBox()
        self.vector.addItems(["Remove drawings fully inside a region", "Remove drawings touching a region"])
        grid.addWidget(self.vector, 3, 1, 1, 2)
        lay.addLayout(grid)
        self.sanitise = QCheckBox("Also remove metadata, JavaScript, attachments and history")
        self.sanitise.setChecked(True)
        self.flatten_all = QCheckBox("Flatten redacted pages fully (maximum safety)")
        self.flatten_all.setToolTip("Each page with a redaction becomes one image: its text is no longer searchable")
        self.ocr_verify = QCheckBox("Check scanned pages with OCR after saving")
        self.ocr_verify.setChecked(True)
        for cb in (self.sanitise, self.flatten_all, self.ocr_verify):
            lay.addWidget(cb)
        lay.addWidget(_notice("Text, image pixels and drawings inside each area are removed from the page; only "
                              "the area becomes an image and the rest of the page stays searchable. If a page "
                              "cannot be cleaned selectively it is flattened automatically and reported. The new "
                              "file is re-opened and verified. The original PDF is never changed."))
        lay.addStretch()
        self.b_apply = _btn("Apply redactions && save", self.apply, obj="danger", ic="check-square")
        lay.addWidget(self.b_apply)
        self.b_view_out = _btn("View the redacted file here", self.view_output)
        self.b_view_out.setEnabled(False)
        lay.addWidget(self.b_view_out)
        return w

    # ------------------------------------------------------------ modes

    def set_mode(self, mode: str, user: bool = False) -> None:
        self.mode = mode
        tool = ALL_TOOLS[mode][1]
        self.title.setText(tool.name)
        self.title_icon.setPixmap(pixmap(tool.icon, theme.ERROR, 32))
        self.desc.setText(tool.summary + "  Marked areas are shared by Mark, Find, Smart detect, Review and Apply.")
        self.mode_buttons[mode].setChecked(True)
        self.panels.setCurrentIndex(self.panel_index[mode])
        if mode in ("review", "apply"):
            self.refresh()
        if user:
            self.mode_changed.emit(mode)

    # ------------------------------------------------------------ open

    def confirm_discard(self) -> bool:
        if self.ctl.marks and self.unsaved:
            return QMessageBox.question(
                self, "Secure Redaction", f"There are {len(self.ctl.marks)} marked area(s) that have not been "
                "applied. Discard them?") == QMessageBox.StandardButton.Yes
        return True

    def _busy(self) -> bool:
        return self.runner is not None and self.runner.busy

    def open_pdf(self, path: Optional[str] = None, output_view: bool = False) -> None:
        if self._busy():
            return
        if not path:
            path, _ = QFileDialog.getOpenFileName(self, "Open PDF to redact", "", "PDF files (*.pdf)")
            if not path:
                return
        if not self.confirm_discard():
            return
        path = os.path.normpath(path)
        password = ""
        try:
            doc = pymupdf.open(path)
        except Exception as exc:
            QMessageBox.critical(self, "Secure Redaction", f"'{Path(path).name}' could not be opened:\n{exc}")
            return
        if doc.needs_pass:
            for attempt in range(3):
                pw, ok = QInputDialog.getText(self, "Password needed",
                                              f"'{Path(path).name}' is password-protected.\nEnter its password"
                                              + (" (incorrect - try again)" if attempt else "") + ":",
                                              QLineEdit.EchoMode.Password)
                if not ok:
                    doc.close()
                    return
                if doc.authenticate(pw):
                    password = pw
                    break
            else:
                doc.close()
                QMessageBox.warning(self, "Password", "The password was not accepted.")
                return
        if self.doc is not None:
            self.doc.close()
        self.doc, self.path, self.password = doc, path, password
        self.cur, self.focus, self.unsaved = 0, None, False
        self.ctl.reset()
        self.find_results, self.smart_results, self.ocr_cache = [], [], {}
        self.find_tree.clear()
        self.smart_tree.clear()
        self.smart_count.setText("Not scanned yet.")
        self.banner.setVisible(output_view)
        self.banner.setText("Viewing the redacted output: black areas are completed redactions. Areas you mark "
                            "here create another redacted copy.")
        stem = Path(path).stem
        self.out_name.setText(f"{stem}_redacted.pdf" if not stem.endswith("_redacted") else f"{stem}_2.pdf")
        scanned = sum(1 for i in range(min(5, doc.page_count)) if not doc[i].get_text("text").strip())
        self.status.setText(f"Opened {Path(path).name} ({doc.page_count} pages)."
                            + (" Scanned pages found - Find and Smart detect will read them with OCR."
                               if scanned else ""))
        self.fit_width()
        self.refresh()

    # ------------------------------------------------------------ rendering

    def render(self, keep_scroll: bool = False) -> None:
        if self.doc is None:
            self.view.show_empty()
            return
        hs, vs = self.view.horizontalScrollBar(), self.view.verticalScrollBar()
        fx = hs.value() / max(1, hs.maximum()) if keep_scroll else 0
        fy = vs.value() / max(1, vs.maximum()) if keep_scroll else 0
        page = self.doc[self.cur]
        scale = self.zoom * SCREEN
        dpr = max(1.0, self.view.devicePixelRatioF())
        pix = page.get_pixmap(matrix=pymupdf.Matrix(scale * dpr, scale * dpr), alpha=False)
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888).copy()
        pm = QPixmap.fromImage(img)
        pm.setDevicePixelRatio(dpr)
        self.view.set_page(pm, pix.width / dpr, pix.height / dpr)
        self.refresh_overlays()
        if keep_scroll:
            hs.setValue(int(fx * hs.maximum()))
            vs.setValue(int(fy * vs.maximum()))
        else:
            vs.setValue(0)

    def to_scene(self, page, rect) -> QRectF:
        r = pymupdf.Rect(rect) * page.rotation_matrix
        s = self.zoom * SCREEN
        return QRectF(r.x0 * s, r.y0 * s, r.width * s, r.height * s)

    def to_pdf(self, page, qrect: QRectF) -> pymupdf.Rect:
        """Scene (screen) rectangle -> unrotated PDF page rectangle."""
        s = self.zoom * SCREEN
        visible = pymupdf.Rect(qrect.left() / s, qrect.top() / s, qrect.right() / s, qrect.bottom() / s)
        r = visible * page.derotation_matrix
        r.normalize()
        return r & (page.rect * page.derotation_matrix)

    def refresh_overlays(self) -> None:
        if self.doc is None:
            return
        page = self.doc[self.cur]
        marked = self.ctl.keys()
        items = []
        for res in self.find_results + self.smart_results:
            if res["page"] == self.cur and rect_key(res["page"], res["rect"]) not in marked:
                items.append((self.to_scene(page, res["rect"]), "candidate", 0))
        for m in self.ctl.marks:
            if m.page == self.cur:
                items.append((self.to_scene(page, m.rect), "approved" if m.approved else "excluded", m.id))
        if self.focus and self.focus[0] == self.cur:
            items.append((self.to_scene(page, self.focus[1]), "focus", 0))
        self.view.set_overlays(items)

    # ------------------------------------------------------------ navigation

    def goto(self, index: int) -> None:
        if self.doc is None:
            return
        index = max(0, min(self.doc.page_count - 1, index))
        changed = index != self.cur
        self.cur = index
        self.render(keep_scroll=not changed)
        self.update_ui()

    def prev_page(self) -> None:
        if self.doc is not None and self.cur > 0:
            self.goto(self.cur - 1)

    def next_page(self) -> None:
        if self.doc is not None and self.cur < self.doc.page_count - 1:
            self.goto(self.cur + 1)

    def jump(self) -> None:
        if self.doc is None:
            return
        try:
            n = int(self.page_edit.text())
        except ValueError:
            n = 0
        if not 1 <= n <= self.doc.page_count:
            QMessageBox.warning(self, "Secure Redaction", f"Enter a page number from 1 to {self.doc.page_count}.")
            self.update_ui()
            return
        self.goto(n - 1)

    def set_zoom(self, z: float, keep: bool = True) -> None:
        self.zoom = max(0.1, min(6.0, z))
        self.render(keep_scroll=keep)
        self.update_ui()

    def zoom_step(self, d: int) -> None:
        if self.doc is None:
            return
        if d > 0:
            nxt = [z for z in ZOOM_LEVELS if z > self.zoom + 1e-3]
            self.set_zoom(nxt[0] if nxt else ZOOM_LEVELS[-1])
        else:
            prv = [z for z in ZOOM_LEVELS if z < self.zoom - 1e-3]
            self.set_zoom(prv[-1] if prv else ZOOM_LEVELS[0])

    def fit_width(self) -> None:
        if self.doc is not None:
            w = self.doc[self.cur].rect.width * SCREEN
            self.set_zoom(max(200, self.view.viewport().width() - 50) / w, keep=False)

    # ------------------------------------------------------------ marks

    def on_rect_drawn(self, qrect: QRectF) -> None:
        if self.doc is None:
            return
        r = self.to_pdf(self.doc[self.cur], qrect)
        if not r.is_empty:
            self.add_marks([(self.cur, tuple(r), "Manual", "Manual area", None)])

    def on_mark_changed(self, mid: int, qrect: QRectF) -> None:
        if not qrect.isNull() and self.doc is not None:
            r = self.to_pdf(self.doc[self.cur], qrect)
            if not r.is_empty:
                self.ctl.modify(mid, tuple(r))
                self.unsaved = True
        self.refresh()

    def add_default_box(self) -> None:
        if self.doc is None:
            return
        centre = self.view.mapToScene(self.view.viewport().rect().center())
        s = self.zoom * SCREEN
        q = QRectF(centre.x() - 60 * s, centre.y() - 12 * s, 120 * s, 24 * s)
        if self.view.page_item is not None:
            q = q.intersected(self.view.page_item.sceneBoundingRect())
        if q.width() > 2 and q.height() > 2:
            self.on_rect_drawn(q)
            self.status.setText("Box added - drag it into place and resize it from the corner.")

    def add_marks(self, specs: list[tuple]) -> int:
        n = self.ctl.add(specs)
        if n:
            self.unsaved = True
        self.refresh()
        return n

    def remove_marks(self, marks, message: str = "") -> None:
        marks = [m for m in marks if m is not None]
        if self.ctl.remove(marks):
            self.unsaved = True
            if message:
                self.status.setText(message)
        self.refresh()

    def undo(self) -> None:
        self.status.setText(self.ctl.undo())
        self.refresh()

    def clear_page(self) -> None:
        marks = [m for m in self.ctl.marks if m.page == self.cur]
        if not marks:
            self.status.setText("No marked areas on this page.")
            return
        self.remove_marks(marks, f"Cleared {len(marks)} area(s) on page {self.cur + 1} (Undo restores them).")

    def clear_all(self) -> None:
        if self.ctl.marks and QMessageBox.question(
                self, "Secure Redaction", f"Remove all {len(self.ctl.marks)} marked area(s)?") \
                == QMessageBox.StandardButton.Yes:
            self.remove_marks(list(self.ctl.marks), "All marked areas removed (Undo restores them).")

    def show_location(self, page: int, rect) -> None:
        self.focus = (page, rect)
        if page != self.cur:
            self.goto(page)
        else:
            self.refresh_overlays()
        self.view.ensureVisible(self.to_scene(self.doc[page], rect), 80, 80)

    # ------------------------------------------------------------ background jobs

    def _start(self, fn, kwargs: dict, on_done, text: str) -> None:
        from .jobs import JobRunner
        if self.runner is None:
            self.runner = JobRunner(self)
            self.runner.progressed.connect(self._on_progress)
            self.runner.finished.connect(self._on_finished)
        self._on_done = on_done
        self.progress.setRange(0, 0)
        self.progress.setVisible(True)
        self.cancel_btn.setVisible(True)
        self.cancel_btn.setEnabled(True)
        self.status.setText(text)
        self.update_ui()
        self.runner.start(fn, kwargs, heavy=True)

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
        on_done, self._on_done = self._on_done, None
        self.update_ui()
        if status == "cancelled":
            self.status.setText("Cancelled.")
        elif status == "error":
            self.status.setText("Stopped - see the message.")
            QMessageBox.warning(self, "Secure Redaction", str(payload))
        elif on_done is not None:
            on_done(payload)

    # ------------------------------------------------------------ find & smart

    def _lang(self, combo: QComboBox) -> str:
        return LANGUAGE_CHOICES.get(combo.currentText(), "eng")

    def run_find(self) -> None:
        if self.doc is None or self._busy():
            return
        terms = [t for t in self.find_edit.toPlainText().splitlines() if t.strip()]
        if not terms:
            QMessageBox.information(self, "Find & Redact", "Enter at least one term to search for.")
            return
        from .services import redaction
        self._start(redaction.find, dict(path=self.path, password=self.password, terms=terms,
                                         match_case=self.f_case.isChecked(), whole_word=self.f_word.isChecked(),
                                         flexible_spaces=self.f_space.isChecked(), ocr_mode=self.f_ocr.currentText(),
                                         ocr_lang=self._lang(self.f_lang), ocr_cache=self.ocr_cache),
                    self.on_found, "Searching…")

    def _scan_notes(self, result: dict) -> str:
        notes = []
        if result.get("ocr_pages"):
            notes.append(f"{len(result['ocr_pages'])} scanned page(s) read with OCR - check the boxes on the page.")
        if result.get("no_text"):
            notes.append(f"No readable text on page(s) {', '.join(map(str, result['no_text'][:15]))}"
                         " - mark those by hand.")
        if result.get("truncated"):
            notes.append("Stopped at 20,000 results.")
        return (" " + " ".join(notes)) if notes else ""

    def on_found(self, result: dict) -> None:
        self.ocr_cache.update(result.get("ocr_cache", {}))
        self.find_results = result["results"]
        self.fill_find()
        n, pages = len(self.find_results), len({r["page"] for r in self.find_results})
        self.find_count.setText((f"{n} match(es) on {pages} page(s). Untick any that should stay, then add them."
                                 if n else "No matches found.") + self._scan_notes(result))
        self.status.setText(f"Search finished: {n} match(es).")
        self.refresh_overlays()

    def _value(self, text: str, show: bool) -> str:
        return text if show else mask_value(text)

    def fill_find(self) -> None:
        self.find_tree.clear()
        show = self.f_show.isChecked()
        for i, r in enumerate(self.find_results):
            ctx = r["context"] if show else r["context"].replace(r["text"], mask_value(r["text"]))
            item = QTreeWidgetItem(["", "", self._value(r["text"], show), ctx + ("  (OCR)" if r.get("ocr") else "")])
            item.setData(1, Qt.ItemDataRole.DisplayRole, r["page"] + 1)
            item.setData(0, Qt.ItemDataRole.UserRole, i)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0, Qt.CheckState.Checked)
            self.find_tree.addTopLevelItem(item)

    def run_scan(self) -> None:
        if self.doc is None or self._busy():
            return
        cats = [c for c, cb in self.cat_boxes.items() if cb.isChecked()]
        if not cats:
            QMessageBox.warning(self, "Smart Redaction", "Select at least one category.")
            return
        from .services import redaction
        self._start(redaction.scan, dict(path=self.path, password=self.password, categories=cats,
                                         ocr_mode=self.s_ocr.currentText(), ocr_lang=self._lang(self.s_lang),
                                         ocr_cache=self.ocr_cache, pan_any_case=self.s_pan_case.isChecked(),
                                         bank_require_keyword=self.s_bank_kw.isChecked()),
                    self.on_scanned, "Scanning for personal data…")

    def on_scanned(self, result: dict) -> None:
        self.ocr_cache.update(result.get("ocr_cache", {}))
        self.smart_results = result["results"]
        for r in self.smart_results:
            r["checked"] = r["conf"] in ("High", "Medium")
        self.fill_smart()
        counts: dict[str, int] = {}
        for r in self.smart_results:
            counts[r["cat"]] = counts.get(r["cat"], 0) + 1
        summary = ", ".join(f"{c} {counts[c]}" for c in SMART_CATEGORIES if c in counts)
        msg = (f"{len(self.smart_results)} item(s): {summary}. High and Medium are ticked; Low ones need a look."
               if self.smart_results else "Nothing found.")
        self.smart_count.setText(msg + self._scan_notes(result))
        self.status.setText(f"Scan finished: {len(self.smart_results)} item(s).")
        self.refresh_overlays()

    def fill_smart(self) -> None:
        self.smart_tree.blockSignals(True)
        self.smart_tree.clear()
        show = self.s_show.isChecked()
        flt = self.s_filter.currentText()
        for i, r in enumerate(self.smart_results):
            if flt != "All categories" and r["cat"] != flt:
                continue
            item = QTreeWidgetItem(["", r["cat"], self._value(r["text"], show), "", r["conf"],
                                    r["note"] + ("  (OCR)" if r.get("ocr") else "")])
            item.setData(3, Qt.ItemDataRole.DisplayRole, r["page"] + 1)
            item.setData(0, Qt.ItemDataRole.UserRole, i)
            item.setToolTip(5, r["note"])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0, Qt.CheckState.Checked if r.get("checked") else Qt.CheckState.Unchecked)
            self.smart_tree.addTopLevelItem(item)
        self.smart_tree.blockSignals(False)

    def _smart_ticked(self, item: QTreeWidgetItem, col: int) -> None:
        if col == 0:
            self.smart_results[item.data(0, Qt.ItemDataRole.UserRole)]["checked"] = \
                item.checkState(0) == Qt.CheckState.Checked

    def tick(self, tree: QTreeWidget, on: bool) -> None:
        for i in range(tree.topLevelItemCount()):
            tree.topLevelItem(i).setCheckState(0, Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)

    def tick_high(self) -> None:
        for i in range(self.smart_tree.topLevelItemCount()):
            item = self.smart_tree.topLevelItem(i)
            r = self.smart_results[item.data(0, Qt.ItemDataRole.UserRole)]
            item.setCheckState(0, Qt.CheckState.Checked if r["conf"] == "High" else Qt.CheckState.Unchecked)

    def on_candidate(self, item, results) -> None:
        if item is not None and self.doc is not None:
            r = results[item.data(0, Qt.ItemDataRole.UserRole)]
            self.show_location(r["page"], r["rect"])

    def _ticked(self, tree: QTreeWidget, results: list[dict]) -> list[dict]:
        return [results[tree.topLevelItem(i).data(0, Qt.ItemDataRole.UserRole)]
                for i in range(tree.topLevelItemCount())
                if tree.topLevelItem(i).checkState(0) == Qt.CheckState.Checked]

    def add_found(self) -> None:
        rows = self._ticked(self.find_tree, self.find_results)
        if not rows:
            QMessageBox.information(self, "Find & Redact", "No matches are ticked.")
            return
        n = self.add_marks([(r["page"], r["rect"], "Find", r["text"], r["text"]) for r in rows])
        self.status.setText(f"{n} match(es) added to the redaction list - check them in Review.")

    def add_smart(self) -> None:
        rows = [r for r in self.smart_results if r.get("checked")]
        if not rows:
            QMessageBox.information(self, "Smart Redaction", "No detected items are ticked.")
            return
        n = self.add_marks([(r["page"], r["rect"], r["cat"], r["text"], r["text"]) for r in rows])
        self.status.setText(f"{n} item(s) added to the redaction list"
                            + ("" if n == len(rows) else f" ({len(rows) - n} were already listed)")
                            + " - check them in Review.")

    # ------------------------------------------------------------ review

    def fill_review(self) -> None:
        self.review_tree.blockSignals(True)
        self.review_tree.clear()
        show = self.r_show.isChecked()
        for m in sorted(self.ctl.marks, key=lambda x: (x.page, x.rect[1], x.rect[0])):
            value = self._value(m.text, show) if m.text else m.label
            item = QTreeWidgetItem(["", "", m.source, value])
            item.setData(1, Qt.ItemDataRole.DisplayRole, m.page + 1)
            item.setData(0, Qt.ItemDataRole.UserRole, m.id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0, Qt.CheckState.Checked if m.approved else Qt.CheckState.Unchecked)
            self.review_tree.addTopLevelItem(item)
        self.review_tree.blockSignals(False)

    def on_review_tick(self, item: QTreeWidgetItem, col: int) -> None:
        if col == 0:
            m = self.ctl.get(item.data(0, Qt.ItemDataRole.UserRole))
            if m:
                self.ctl.set_approved([m], item.checkState(0) == Qt.CheckState.Checked)
                self.unsaved = True
                self.refresh(review=False)

    def on_review_select(self, cur, _prev) -> None:
        if cur is not None:
            m = self.ctl.get(cur.data(0, Qt.ItemDataRole.UserRole))
            if m:
                self.show_location(m.page, m.rect)

    def approve_all(self, value: bool) -> None:
        self.ctl.set_approved(list(self.ctl.marks), value)
        self.refresh()

    def remove_review_selected(self) -> None:
        item = self.review_tree.currentItem()
        if item is not None:
            self.remove_marks([self.ctl.get(item.data(0, Qt.ItemDataRole.UserRole))],
                              "Area removed (Undo restores it).")

    # ------------------------------------------------------------ apply

    def _browse_out(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Save the redacted PDF to")
        if folder:
            self.out_dir.setText(folder)

    def _target(self) -> Optional[Path]:
        from .services.common import safe_filename, unique_path
        folder = Path(self.out_dir.text().strip() or Path(self.path).parent)
        if not folder.is_dir():
            QMessageBox.warning(self, "Apply Redactions", f"The folder does not exist:\n{folder}")
            return None
        name = safe_filename(self.out_name.text()) or f"{Path(self.path).stem}_redacted.pdf"
        if not name.lower().endswith(".pdf"):
            name += ".pdf"
        return unique_path(folder / name)

    def apply(self) -> None:
        if self.doc is None or self._busy():
            return
        approved = [m for m in self.ctl.marks if m.approved]
        if not approved:
            QMessageBox.information(self, "Apply Redactions", "There are no approved areas to apply.")
            return
        target = self._target()
        if target is None:
            return
        regions: dict[int, list] = {}
        for m in approved:
            regions.setdefault(m.page, []).append(m.rect)
        excluded = len(self.ctl.marks) - len(approved)
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Confirm permanent redaction")
        box.setText(f"<b>Remove {len(approved)} area(s) on {len(regions)} page(s)?</b>")
        box.setInformativeText(f"Content inside these areas will be permanently removed in the new file:\n{target}\n\n"
                               "The original PDF stays unchanged."
                               + (f"\n{excluded} excluded area(s) will be ignored." if excluded else "")
                               + ("\nEvery redacted page will be flattened (text no longer searchable)."
                                  if self.flatten_all.isChecked() else ""))
        go = box.addButton("Apply redactions", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        if box.clickedButton() is not go:
            return
        terms = sorted({m.text for m in approved if m.text})
        lang = LANGUAGE_CHOICES.get(self.s_lang.currentText(), "eng")
        from .services import redaction
        self._start(redaction.apply, dict(src_path=self.path, password=self.password, regions=regions,
                                          out_path=str(target), dpi=int(self.dpi.currentText().split()[0]),
                                          vector=self.vector.currentText(), sanitise=self.sanitise.isChecked(),
                                          flatten_all=self.flatten_all.isChecked(), terms=terms,
                                          approved=len(approved), ocr_verify=self.ocr_verify.isChecked(),
                                          ocr_lang=lang),
                    self.on_applied, "Applying redactions…")

    def on_applied(self, result: dict) -> None:
        self.unsaved = False
        self.ctl.last_terms = sorted({m.text for m in self.ctl.marks if m.approved and m.text})
        self.ctl.last_output = result["out"]
        self.b_view_out.setEnabled(True)
        self.status.setText(("Redacted PDF saved and verified: " if not result["failed"]
                             else "Redacted PDF saved but VERIFICATION FAILED: ") + result["out"])
        RedactionSummaryDialog(self, result, self.request_verify).exec()

    def request_verify(self) -> None:
        if self.ctl.last_output:
            self.verify_requested.emit(self.ctl.last_output, list(self.ctl.last_terms))

    def view_output(self) -> None:
        if self.ctl.last_output and os.path.isfile(self.ctl.last_output):
            self.unsaved = False
            self.open_pdf(self.ctl.last_output, output_view=True)

    # ------------------------------------------------------------ refresh

    def refresh(self, review: bool = True) -> None:
        self.refresh_overlays()
        if review:
            self.fill_review()
        n, ok = len(self.ctl.marks), sum(1 for m in self.ctl.marks if m.approved)
        pages = len({m.page for m in self.ctl.marks if m.approved})
        self.mode_buttons["review"].setText(f"{MODE_TITLES['review']} ({n})")
        for m in MODES:
            if m != "review":
                self.mode_buttons[m].setText(MODE_TITLES[m])
        self.review_count.setText(f"{n} marked area(s): {ok} approved, {n - ok} excluded.")
        self.manual_count.setText(f"Marked areas on this page: {sum(1 for m in self.ctl.marks if m.page == self.cur)}"
                                  f"   |   in total: {n}")
        self.apply_summary.setText(f"{ok} approved area(s) on {pages} page(s) will be removed in a new PDF."
                                   if ok else "No approved areas yet - mark, find or detect content first.")
        self.update_ui()

    def update_ui(self) -> None:
        has = self.doc is not None
        busy = self._busy()
        for w in (self.b_prev, self.b_next, self.page_edit, self.b_zout, self.b_zin, self.b_fitw):
            w.setEnabled(has)
        self.b_open.setEnabled(not busy)
        self.b_apply.setEnabled(has and not busy and any(m.approved for m in self.ctl.marks))
        self.b_undo.setEnabled(bool(self.ctl.history))
        if has:
            n = self.doc.page_count
            self.page_edit.setText(str(self.cur + 1))
            self.page_total.setText(f"/{n}")
            self.b_prev.setEnabled(self.cur > 0)
            self.b_next.setEnabled(self.cur < n - 1)
            self.zoom_lbl.setText(f"{round(self.zoom * 100)}%")
        else:
            self.page_edit.setText("")
            self.page_total.setText("/0")
