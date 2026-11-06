"""Page workspace for Rearrange Pages: thumbnails that can be dragged into a new
order, rotated or removed before saving."""

from __future__ import annotations

from pathlib import Path

import pymupdf
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QImage, QPixmap, QTransform
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QLabel, QListView, QListWidget, QListWidgetItem,
                               QPushButton, QVBoxLayout, QWidget)

from . import theme
from .icons import icon

THUMB = 150
ROLE_PAGE, ROLE_TURN = Qt.ItemDataRole.UserRole, Qt.ItemDataRole.UserRole + 1


class PageGrid(QListWidget):
    files_dropped = Signal(list)

    def __init__(self):
        super().__init__()
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setIconSize(QSize(THUMB, THUMB))
        self.setGridSize(QSize(THUMB + 26, THUMB + 40))
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setMovement(QListView.Movement.Snap)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setSpacing(6)
        self.setUniformItemSizes(True)
        self.setWordWrap(True)

    # external PDF drops load a document; internal drags reorder pages
    def dragEnterEvent(self, e):
        if e.source() is self:
            super().dragEnterEvent(e)
        elif e.mimeData().hasUrls():
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragMoveEvent(self, e):
        if e.source() is self:
            super().dragMoveEvent(e)
        elif e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        if e.source() is self:
            super().dropEvent(e)
            return
        paths = [Path(u.toLocalFile()) for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.files_dropped.emit(paths)
        e.acceptProposedAction()


class PageWorkspace(QWidget):
    changed = Signal()

    def __init__(self, on_drop):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        bar = QHBoxLayout()
        self.buttons = []
        for text, ic, slot in (("Rotate left", "rotate", lambda: self.turn(270)),
                               ("Rotate right", "rotate", lambda: self.turn(90)),
                               ("Remove", "trash", self.remove), ("Reverse order", "rearrange", self.reverse),
                               ("Reset", "clear", self.reset)):
            b = QPushButton(icon(ic), text)
            b.clicked.connect(slot)
            bar.addWidget(b)
            self.buttons.append(b)
        bar.addStretch()
        lay.addLayout(bar)
        self.hint = QLabel("Drop a PDF here or use Add file. Drag pages to reorder; select pages (Ctrl/Shift "
                           "for several) to rotate or remove them.")
        self.hint.setProperty("role", "hint")
        self.hint.setWordWrap(True)
        lay.addWidget(self.hint)
        self.grid = PageGrid()
        self.grid.files_dropped.connect(on_drop)
        self.grid.model().rowsMoved.connect(lambda *a: self._renumber())
        lay.addWidget(self.grid, 1)
        self.path: Path | None = None
        self.password = ""
        self._base: dict[int, QPixmap] = {}
        self._set_enabled(False)

    def _set_enabled(self, on: bool) -> None:
        for b in self.buttons:
            b.setEnabled(on)

    def load(self, path: Path, password: str = "") -> None:
        self.grid.clear()
        self._base.clear()
        self.path, self.password = path, password
        with pymupdf.open(str(path)) as doc:
            if doc.needs_pass:
                doc.authenticate(password)
            for i, page in enumerate(doc):
                z = THUMB / max(page.rect.width, page.rect.height)
                pix = page.get_pixmap(matrix=pymupdf.Matrix(z, z), alpha=False)
                img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888).copy()
                self._base[i + 1] = QPixmap.fromImage(img)
                item = QListWidgetItem()
                item.setData(ROLE_PAGE, i + 1)
                item.setData(ROLE_TURN, 0)
                self.grid.addItem(item)
        self._renumber()
        self._set_enabled(True)
        self.changed.emit()

    def clear(self) -> None:
        self.grid.clear()
        self._base.clear()
        self.path = None
        self._set_enabled(False)
        self.changed.emit()

    def _paint(self, item: QListWidgetItem) -> None:
        page, turn = item.data(ROLE_PAGE), item.data(ROLE_TURN)
        pm = self._base[page]
        if turn:
            pm = pm.transformed(QTransform().rotate(turn), Qt.TransformationMode.SmoothTransformation)
        item.setIcon(icon_from(framed(pm)))

    def _renumber(self) -> None:
        for row in range(self.grid.count()):
            item = self.grid.item(row)
            page, turn = item.data(ROLE_PAGE), item.data(ROLE_TURN)
            moved = " (moved)" if page != row + 1 else ""
            item.setText(f"{row + 1}.  page {page}{moved}" + (f"  ↻{turn}°" if turn else ""))
            self._paint(item)
        self.changed.emit()

    def turn(self, deg: int) -> None:
        for item in self.grid.selectedItems():
            item.setData(ROLE_TURN, (item.data(ROLE_TURN) + deg) % 360)
        self._renumber()

    def remove(self) -> None:
        for item in self.grid.selectedItems():
            self.grid.takeItem(self.grid.row(item))
        self._renumber()

    def reverse(self) -> None:
        items = [self.grid.takeItem(0) for _ in range(self.grid.count())]
        for item in reversed(items):
            self.grid.addItem(item)
        self._renumber()

    def reset(self) -> None:
        if self.path:
            self.load(self.path, self.password)

    def order(self) -> list[tuple[int, int]]:
        return [(self.grid.item(r).data(ROLE_PAGE), self.grid.item(r).data(ROLE_TURN))
                for r in range(self.grid.count())]

    def summary(self) -> str:
        if not self.path:
            return ""
        order = self.order()
        total = len(self._base)
        changed = order != [(p, 0) for p in range(1, total + 1)]
        removed = total - len(order)
        bits = [f"{len(order)} of {total} pages"]
        if removed:
            bits.append(f"{removed} removed")
        turned = sum(1 for _p, t in order if t)
        if turned:
            bits.append(f"{turned} rotated")
        return ", ".join(bits) + ("" if changed else " - no changes yet")


def framed(pm: QPixmap) -> QPixmap:
    """White pages need an outline (and a soft shadow) to stand out on the white grid."""
    from PySide6.QtGui import QColor, QPainter
    out = QPixmap(pm.width() + 5, pm.height() + 5)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.fillRect(4, 4, pm.width(), pm.height(), QColor(11, 30, 61, 40))
    p.drawPixmap(1, 1, pm)
    p.setPen(QColor(theme.BORDER_STRONG))
    p.drawRect(0, 0, pm.width() + 1, pm.height() + 1)
    p.end()
    return out


def icon_from(pm: QPixmap):
    from PySide6.QtGui import QIcon
    ic = QIcon()
    ic.addPixmap(pm, QIcon.Mode.Normal)
    ic.addPixmap(pm, QIcon.Mode.Selected)
    return ic
