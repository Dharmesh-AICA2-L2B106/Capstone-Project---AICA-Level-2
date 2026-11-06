"""Modern professional UI theme, color constants, and QSS styles.

Adheres to Windows 11 (Fluent Design) & macOS (Human Interface Guidelines)
with tactile 3D borders, interactive hover/press states, and fluid table row-hover effects.
"""

from src.clientdesk_ai.ui.qt_compat import (
    QStyledItemDelegate, QStyleOptionViewItem, QStyle, QTableWidget,
    QPainter, QColor, QtCore
)

MODERN_QSS = """
/* =====================================================================
   GLOBAL WINDOW, FONTS & SURFACE
   ===================================================================== */
QWidget {
    font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, "SF Pro Text", Roboto, "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
    color: #0F172A;
    background-color: #F8FAFC;
}

QLabel {
    background-color: transparent;
}

/* =====================================================================
   SIDEBAR NAVIGATION
   ===================================================================== */
#SidebarWidget {
    background-color: #1E3A8A;
    border-right: 1px solid #1D4ED8;
}

#SidebarTitle {
    color: #FFFFFF;
    font-size: 17px;
    font-weight: 700;
    padding: 20px 18px 4px 18px;
    letter-spacing: -0.2px;
}

#SidebarSubtitle {
    color: #BFDBFE;
    font-size: 11px;
    font-weight: 500;
    padding: 0px 18px 18px 18px;
}

/* Sidebar Navigation Buttons */
#SidebarWidget QPushButton,
QPushButton[class="nav-btn"], QPushButton.nav-btn {
    text-align: left;
    padding: 10px 16px;
    border: none;
    border-left: 3.5px solid transparent;
    border-radius: 6px;
    color: #DBEAFE;
    font-size: 13px;
    font-weight: 500;
    background-color: transparent;
    margin: 2px 0px;
    outline: none;
}

#SidebarWidget QPushButton:hover,
QPushButton[class="nav-btn"]:hover, QPushButton.nav-btn:hover {
    background-color: #2563EB;
    color: #FFFFFF;
}

#SidebarWidget QPushButton:checked,
#SidebarWidget QPushButton[class="nav-btn"]:checked,
QPushButton[class="nav-btn"]:checked, QPushButton.nav-btn:checked {
    background-color: #1D4ED8 !important;
    border-left: 3.5px solid #60A5FA !important;
    color: #FFFFFF !important;
    font-weight: 600 !important;
}

/* =====================================================================
   TOP BAR & HEADER PANELS
   ===================================================================== */
#TopBarWidget {
    background-color: #FFFFFF;
    border-bottom: 1.5px solid #E2E8F0;
    padding: 10px 20px;
}

#PageTitle {
    font-size: 18px;
    font-weight: 700;
    color: #0F172A;
    letter-spacing: -0.2px;
}

/* Cards & Surface Containers */
QFrame[class="card"], QFrame.card {
    background-color: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
}

/* =====================================================================
   MODERN macOS / WINDOWS 11 BUTTONS
   ===================================================================== */

/* Default QPushButton (Standard Neutral Button) */
QPushButton {
    background-color: #FFFFFF;
    color: #1E293B;
    border: 1px solid #CBD5E1;
    border-bottom: 2px solid #94A3B8;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 600;
    font-size: 13px;
    text-align: center;
    min-height: 20px;
    outline: none;
}

QPushButton:hover {
    background-color: #F8FAFC;
    border-color: #94A3B8;
    border-bottom: 2px solid #64748B;
    color: #0F172A;
}

QPushButton:pressed {
    background-color: #F1F5F9;
    border: 1px solid #94A3B8;
    border-top: 2px solid #64748B;
    border-bottom: 1px solid #94A3B8;
    padding-top: 9px;
    padding-bottom: 7px;
}

QPushButton:disabled {
    background-color: #F1F5F9;
    color: #94A3B8;
    border: 1px solid #E2E8F0;
    border-bottom: 1px solid #E2E8F0;
}

/* Sidebar Toggle Icon Button in Top Header Bar */
QPushButton#BtnToggleSidebar {
    background-color: #FFFFFF;
    color: #1E293B;
    border: 1px solid #CBD5E1;
    border-bottom: 2px solid #94A3B8;
    border-radius: 6px;
    font-size: 17px;
    font-weight: 700;
    text-align: center;
    padding: 0px;
    min-height: 32px;
    min-width: 32px;
}

QPushButton#BtnToggleSidebar:hover {
    background-color: #F1F5F9;
    border-color: #94A3B8;
    border-bottom: 2px solid #64748B;
    color: #2563EB;
}

QPushButton#BtnToggleSidebar:pressed {
    background-color: #E2E8F0;
    border: 1px solid #94A3B8;
    border-top: 2px solid #64748B;
    border-bottom: 1px solid #94A3B8;
    padding-top: 2px;
}

/* Primary Accent Button (Windows 11 Accent / macOS System Blue) */
QPushButton[class="btn-primary"], QPushButton.btn-primary {
    background-color: #2563EB;
    color: #FFFFFF;
    border: 1px solid #1D4ED8;
    border-bottom: 2px solid #1E40AF;
    border-radius: 6px;
    padding: 8px 18px;
    font-weight: 600;
    font-size: 13px;
    text-align: center;
    min-height: 20px;
    outline: none;
}

QPushButton[class="btn-primary"]:hover, QPushButton.btn-primary:hover {
    background-color: #1D4ED8;
    border-color: #1E40AF;
    border-bottom: 2px solid #172554;
    color: #FFFFFF;
}

QPushButton[class="btn-primary"]:pressed, QPushButton.btn-primary:pressed {
    background-color: #1E40AF;
    border: 1px solid #172554;
    border-top: 2px solid #0F172A;
    border-bottom: 1px solid #172554;
    padding-top: 9px;
    padding-bottom: 7px;
    color: #FFFFFF;
}

QPushButton[class="btn-primary"]:disabled, QPushButton.btn-primary:disabled {
    background-color: #93C5FD;
    border: 1px solid #93C5FD;
    color: #FFFFFF;
}

/* Secondary Neutral Button */
QPushButton[class="btn-secondary"], QPushButton.btn-secondary {
    background-color: #FFFFFF;
    color: #334155;
    border: 1px solid #CBD5E1;
    border-bottom: 2px solid #94A3B8;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 600;
    font-size: 13px;
    text-align: center;
    min-height: 20px;
    outline: none;
}

QPushButton[class="btn-secondary"]:hover, QPushButton.btn-secondary:hover {
    background-color: #F8FAFC;
    border-color: #94A3B8;
    border-bottom: 2px solid #64748B;
    color: #0F172A;
}

QPushButton[class="btn-secondary"]:pressed, QPushButton.btn-secondary:pressed {
    background-color: #F1F5F9;
    border: 1px solid #94A3B8;
    border-top: 2px solid #64748B;
    border-bottom: 1px solid #94A3B8;
    padding-top: 9px;
    padding-bottom: 7px;
}

/* Success Button (Modern Emerald Green) */
QPushButton[class="btn-success"], QPushButton.btn-success {
    background-color: #059669;
    color: #FFFFFF;
    border: 1px solid #047857;
    border-bottom: 2px solid #065F46;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 600;
    font-size: 13px;
    text-align: center;
    min-height: 20px;
    outline: none;
}

QPushButton[class="btn-success"]:hover, QPushButton.btn-success:hover {
    background-color: #047857;
    border-color: #065F46;
    border-bottom: 2px solid #022C22;
    color: #FFFFFF;
}

QPushButton[class="btn-success"]:pressed, QPushButton.btn-success:pressed {
    background-color: #047857;
    border: 1px solid #065F46;
    border-top: 2px solid #022C22;
    border-bottom: 1px solid #065F46;
    padding-top: 9px;
    padding-bottom: 7px;
    color: #FFFFFF;
}

/* Danger Button (Modern Crimson Red) */
QPushButton[class="btn-danger"], QPushButton.btn-danger {
    background-color: #DC2626;
    color: #FFFFFF;
    border: 1px solid #B91C1C;
    border-bottom: 2px solid #991B1B;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 600;
    font-size: 13px;
    text-align: center;
    min-height: 20px;
    outline: none;
}

QPushButton[class="btn-danger"]:hover, QPushButton.btn-danger:hover {
    background-color: #B91C1C;
    border-color: #991B1B;
    border-bottom: 2px solid #450A0A;
    color: #FFFFFF;
}

QPushButton[class="btn-danger"]:pressed, QPushButton.btn-danger:pressed {
    background-color: #B91C1C;
    border: 1px solid #991B1B;
    border-top: 2px solid #450A0A;
    border-bottom: 1px solid #991B1B;
    padding-top: 9px;
    padding-bottom: 7px;
    color: #FFFFFF;
}

/* Compact Table Action Buttons */
QPushButton[class="btn-table-primary"], QPushButton.btn-table-primary {
    background-color: #2563EB;
    color: #FFFFFF;
    font-weight: 600;
    font-size: 11px;
    border: 1px solid #1D4ED8;
    border-bottom: 2px solid #1E40AF;
    border-radius: 5px;
    padding: 4px 10px;
    text-align: center;
    outline: none;
    min-height: 20px;
    min-width: 65px;
}

QPushButton[class="btn-table-primary"]:hover, QPushButton.btn-table-primary:hover {
    background-color: #1D4ED8;
    border-color: #1E40AF;
    border-bottom: 2px solid #172554;
    color: #FFFFFF;
}

QPushButton[class="btn-table-primary"]:pressed, QPushButton.btn-table-primary:pressed {
    background-color: #1E40AF;
    border-top: 1px solid #0F172A;
    padding-top: 5px;
    padding-bottom: 3px;
}

QPushButton[class="btn-table-secondary"], QPushButton.btn-table-secondary {
    background-color: #FFFFFF;
    color: #1E293B;
    font-weight: 600;
    font-size: 11px;
    border: 1px solid #CBD5E1;
    border-bottom: 2px solid #94A3B8;
    border-radius: 5px;
    padding: 4px 10px;
    text-align: center;
    outline: none;
    min-height: 20px;
    min-width: 55px;
}

QPushButton[class="btn-table-secondary"]:hover, QPushButton.btn-table-secondary:hover {
    background-color: #F8FAFC;
    border-color: #94A3B8;
    border-bottom: 2px solid #64748B;
    color: #0F172A;
}

QPushButton[class="btn-table-secondary"]:pressed, QPushButton.btn-table-secondary:pressed {
    background-color: #F1F5F9;
    border: 1px solid #94A3B8;
    border-top: 1px solid #64748B;
    padding-top: 5px;
    padding-bottom: 3px;
}

/* =====================================================================
   FORM CONTROLS
   ===================================================================== */
QLineEdit, QComboBox, QDateEdit {
    background-color: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    padding: 3px 10px;
    color: #0F172A;
    font-size: 13px;
    selection-background-color: #2563EB;
    selection-color: #FFFFFF;
    min-height: 28px;
}

QTextEdit {
    background-color: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    padding: 8px 10px;
    color: #0F172A;
    selection-background-color: #2563EB;
    selection-color: #FFFFFF;
}

QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QDateEdit:focus {
    border: 1.5px solid #2563EB;
    background-color: #FFFFFF;
}

QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 24px;
    border-left: 1px solid #E2E8F0;
}

/* =====================================================================
   SPLITTERS & SCROLL CONTAINERS
   ===================================================================== */
QSplitter::handle:horizontal {
    background-color: transparent;
    width: 6px;
}

QSplitter::handle:horizontal:hover {
    background-color: #CBD5E1;
    border-radius: 3px;
}

QScrollArea {
    background-color: transparent;
    border: none;
}

/* =====================================================================
   MODERN macOS / WINDOWS 11 TABLE STYLING
   ===================================================================== */
QTableWidget, QTableView {
    background-color: #FFFFFF;
    alternate-background-color: #FAFCFE;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    gridline-color: transparent;
    selection-background-color: #EFF6FF;
    selection-color: #1E3A8A;
    outline: none;
}

QTableWidget:focus, QTableView:focus {
    outline: none;
    border: 1px solid #CBD5E1;
}

QTableWidget::item, QTableView::item {
    padding: 4px 8px;
    border: none;
    border-bottom: 1px solid #F1F5F9;
    outline: none;
}

QTableWidget::item:focus, QTableView::item:focus {
    outline: none;
    border: none;
}

QTableWidget::item:hover, QTableView::item:hover {
    background-color: #F8FAFC;
    color: #0F172A;
}

QTableWidget::item:selected, QTableView::item:selected {
    background-color: #EFF6FF;
    color: #1E3A8A;
    font-weight: 600;
    outline: none;
    border: none;
}

QTableWidget::item:selected:hover, QTableView::item:selected:hover {
    background-color: #DBEAFE;
    color: #1E3A8A;
}

/* Table Header */
QHeaderView {
    background-color: transparent;
    border: none;
}

QHeaderView::section {
    background-color: #F8FAFC;
    color: #475569;
    font-weight: 600;
    font-size: 12px;
    letter-spacing: 0.3px;
    padding: 10px 12px;
    border: none;
    border-bottom: 1.5px solid #E2E8F0;
    border-right: 1px solid #F1F5F9;
}

QHeaderView::section:hover {
    background-color: #EDF2F7;
    color: #0F172A;
}

/* Progress Bar */
QProgressBar {
    background-color: #E2E8F0;
    border: none;
    border-radius: 5px;
    text-align: center;
    color: #0F172A;
    font-weight: 600;
    font-size: 11px;
}

QProgressBar::chunk {
    background-color: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:0, stop:0 #10B981, stop:1 #059669);
    border-radius: 5px;
}

/* =====================================================================
   SLEEK OVERLAY SCROLLBARS (macOS / Windows 11 style)
   ===================================================================== */
QScrollBar:vertical {
    border: none;
    background: transparent;
    width: 8px;
    margin: 4px 1px 4px 1px;
    border-radius: 4px;
}

QScrollBar::handle:vertical {
    background: #CBD5E1;
    min-height: 24px;
    border-radius: 4px;
}

QScrollBar::handle:vertical:hover {
    background: #94A3B8;
}

QScrollBar::handle:vertical:pressed {
    background: #64748B;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: none;
    border: none;
    height: 0px;
}

QScrollBar:horizontal {
    border: none;
    background: transparent;
    height: 8px;
    margin: 1px 4px 1px 4px;
    border-radius: 4px;
}

QScrollBar::handle:horizontal {
    background: #CBD5E1;
    min-width: 24px;
    border-radius: 4px;
}

QScrollBar::handle:horizontal:hover {
    background: #94A3B8;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: none;
    border: none;
    width: 0px;
}
"""

STATUS_BADGE_STYLES = {
    "MANDATORY": "background-color: #FEE2E2; color: #991B1B; font-weight: 700; font-size: 11px; border-radius: 4px; padding: 2px 8px;",
    "CONDITIONAL": "background-color: #E0E7FF; color: #3730A3; font-weight: 700; font-size: 11px; border-radius: 4px; padding: 2px 8px;",
    "OPTIONAL": "background-color: #F1F5F9; color: #475569; font-weight: 600; font-size: 11px; border-radius: 4px; padding: 2px 8px;",
    "ACCEPTED": "background-color: #D1FAE5; color: #065F46; font-weight: 700; font-size: 11px; border-radius: 4px; padding: 2px 8px;",
    "DEFICIENT": "background-color: #FEE2E2; color: #B91C1C; font-weight: 700; font-size: 11px; border-radius: 4px; padding: 2px 8px;",
    "WAIVED_WITH_APPROVAL": "background-color: #FEF3C7; color: #92400E; font-weight: 700; font-size: 11px; border-radius: 4px; padding: 2px 8px;",
    "NOT_REQUESTED": "background-color: #F1F5F9; color: #64748B; font-weight: 500; font-size: 11px; border-radius: 4px; padding: 2px 8px;",
    "REQUESTED": "background-color: #FEF9C3; color: #854D0E; font-weight: 600; font-size: 11px; border-radius: 4px; padding: 2px 8px;",
    "RECEIVED": "background-color: #E0F2FE; color: #0369A1; font-weight: 600; font-size: 11px; border-radius: 4px; padding: 2px 8px;",
    "UNDER_VERIFICATION": "background-color: #F3E8FF; color: #6B21A8; font-weight: 600; font-size: 11px; border-radius: 4px; padding: 2px 8px;",
    "NOT_APPLICABLE": "background-color: #F1F5F9; color: #64748B; font-weight: 600; font-size: 11px; border-radius: 4px; padding: 2px 8px; border: 1px dashed #CBD5E1;",
}

SERVICE_BADGE_STYLES = {
    "GST": "background-color: #ECFDF5; color: #047857; border: 1px solid #A7F3D0; font-weight: 600; font-size: 11px; border-radius: 4px; padding: 2px 6px;",
    "ITR": "background-color: #EFF6FF; color: #1D4ED8; border: 1px solid #BFDBFE; font-weight: 600; font-size: 11px; border-radius: 4px; padding: 2px 6px;",
    "Company Formation": "background-color: #F5F3FF; color: #6D28D9; border: 1px solid #DDD6FE; font-weight: 600; font-size: 11px; border-radius: 4px; padding: 2px 6px;",
    "Partnership Registration": "background-color: #FFFBEB; color: #B45309; border: 1px solid #FDE68A; font-weight: 600; font-size: 11px; border-radius: 4px; padding: 2px 6px;",
    "LLP Incorporation": "background-color: #F0FDFA; color: #0F766E; border: 1px solid #99F6E4; font-weight: 600; font-size: 11px; border-radius: 4px; padding: 2px 6px;",
    "MCA Annual Compliance": "background-color: #FFF1F2; color: #BE123C; border: 1px solid #FECDD3; font-weight: 600; font-size: 11px; border-radius: 4px; padding: 2px 6px;",
}


def get_service_badge_style(service_name_or_group: str) -> str:
    """Return distinct color-coded styling for statutory service groups."""
    txt = (service_name_or_group or "").lower()
    if "gst" in txt:
        return SERVICE_BADGE_STYLES["GST"]
    if "itr" in txt or "income" in txt or "salaried" in txt or "business" in txt:
        return SERVICE_BADGE_STYLES["ITR"]
    if "company" in txt or "pvt" in txt or "opc" in txt:
        return SERVICE_BADGE_STYLES["Company Formation"]
    if "partnership" in txt:
        return SERVICE_BADGE_STYLES["Partnership Registration"]
    if "llp" in txt:
        return SERVICE_BADGE_STYLES["LLP Incorporation"]
    if "mca" in txt or "roc" in txt or "annual compliance" in txt:
        return SERVICE_BADGE_STYLES["MCA Annual Compliance"]
    return "background-color: #F1F5F9; color: #334155; border: 1px solid #CBD5E1; font-weight: 600; border-radius: 4px; padding: 3px 8px;"


class ModernTableDelegate(QStyledItemDelegate):
    """Modern macOS / Windows 11 table item delegate.

    Features:
    - Eliminates dotted/solid cell focus rectangle artifacts.
    - Smooth full-row hover tracking with soft slate highlight.
    - Windows 11 / macOS selection styling with vertical left-edge accent pill.
    - Clean typography and vertical centering.
    """

    def __init__(self, table: QTableWidget):
        super().__init__(table)
        self.table = table
        self.hovered_row = -1

        # Enable mouse tracking on both table and viewport for fluid hover tracking
        self.table.setMouseTracking(True)
        viewport = self.table.viewport()
        if viewport:
            viewport.setMouseTracking(True)
            viewport.installEventFilter(self)

    def eventFilter(self, watched, event):
        viewport = self.table.viewport()
        if watched == viewport:
            event_type = event.type()
            if event_type == QtCore.QEvent.Type.MouseMove:
                pos = event.pos()
                index = self.table.indexAt(pos)
                new_row = index.row() if index.isValid() else -1
                if new_row != self.hovered_row:
                    old_row = self.hovered_row
                    self.hovered_row = new_row
                    if old_row >= 0:
                        self._update_row(old_row)
                    if new_row >= 0:
                        self._update_row(new_row)
            elif event_type in (QtCore.QEvent.Type.Leave, QtCore.QEvent.Type.Hide):
                if self.hovered_row >= 0:
                    old_row = self.hovered_row
                    self.hovered_row = -1
                    self._update_row(old_row)
        return super().eventFilter(watched, event)

    def _update_row(self, row: int):
        cols = self.table.columnCount()
        model = self.table.model()
        if cols > 0 and model:
            tl = model.index(row, 0)
            br = model.index(row, cols - 1)
            self.table.viewport().update(self.table.visualRect(tl).united(self.table.visualRect(br)))

    def drawFocus(self, painter: QPainter, option: QStyleOptionViewItem, rect: QtCore.QRect):
        """Eliminate default dotted/solid cell focus rectangle artifacts completely."""
        pass

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        opt = QStyleOptionViewItem(option)
        # Eliminate cell focus rectangle on Windows & macOS
        opt.state &= ~QStyle.StateFlag.State_HasFocus
        opt.state &= ~QStyle.StateFlag.State_KeyboardFocusChange

        row = index.row()
        col = index.column()
        is_selected = bool(opt.state & QStyle.StateFlag.State_Selected)
        is_hovered = (row == self.hovered_row)

        painter.save()
        rect = opt.rect

        # 1. Background fill
        if is_selected:
            bg_color = QColor("#DBEAFE") if is_hovered else QColor("#EFF6FF")
            painter.fillRect(rect, bg_color)

            # Left accent pill indicator on column 0 (macOS / Windows 11 signature)
            if col == 0:
                pill_height = min(22.0, float(rect.height()) - 14.0)
                pill_y = float(rect.y()) + (float(rect.height()) - pill_height) / 2.0
                pill_rect = QtCore.QRectF(float(rect.x()) + 2.5, pill_y, 3.5, pill_height)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                painter.setPen(QtCore.Qt.PenStyle.NoPen)
                painter.setBrush(QColor("#2563EB"))
                painter.drawRoundedRect(pill_rect, 1.75, 1.75)
        elif is_hovered:
            painter.fillRect(rect, QColor("#F8FAFC"))

        # 2. Subtle bottom divider
        painter.setPen(QColor("#F1F5F9"))
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())
        painter.restore()

        super().paint(painter, opt, index)


# Backward compatibility alias
CleanTableDelegate = ModernTableDelegate


def configure_modern_table(table: QTableWidget) -> None:
    """Configures a QTableWidget with clean row selection, padding, full-row hover, and modern styling."""
    table.setItemDelegate(ModernTableDelegate(table))
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setMouseTracking(True)
    if table.viewport():
        table.viewport().setMouseTracking(True)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(44)
    table.setShowGrid(False)
    table.setAlternatingRowColors(True)
