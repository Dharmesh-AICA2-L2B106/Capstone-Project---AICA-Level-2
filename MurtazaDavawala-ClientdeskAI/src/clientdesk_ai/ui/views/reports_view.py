"""Operational reporting and formatted Excel export view."""

from pathlib import Path
from src.clientdesk_ai.ui.qt_compat import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QFrame, QFileDialog, QMessageBox, Qt
)
from src.clientdesk_ai.reporting.export_service import ReportExportService
from src.clientdesk_ai.config.settings import CONFIG
from src.clientdesk_ai.ui.theme import configure_modern_table


class ReportsView(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # Header
        header_layout = QHBoxLayout()
        title_box = QVBoxLayout()
        title_lbl = QLabel("Operational Compliance Reports & Exports")
        title_lbl.setStyleSheet("font-size: 20px; font-weight: 700; color: #0F172A;")
        sub_lbl = QLabel("Export engagement portfolios, document audits, and staff workloads directly to formatted Excel.")
        sub_lbl.setStyleSheet("font-size: 13px; color: #64748B;")
        title_box.addWidget(title_lbl)
        title_box.addWidget(sub_lbl)
        header_layout.addLayout(title_box)
        header_layout.addStretch()

        btn_export_all = QPushButton("Export All Engagements (.xlsx)")
        btn_export_all.setProperty("class", "btn-primary")
        btn_export_all.clicked.connect(self.export_all_engagements)

        btn_export_active = QPushButton("Export Active Checklist (.xlsx)")
        btn_export_active.setProperty("class", "btn-secondary")
        btn_export_active.clicked.connect(self.export_active_checklist)

        header_layout.addWidget(btn_export_active)
        header_layout.addWidget(btn_export_all)
        layout.addLayout(header_layout)

        # Table
        card = QFrame()
        card.setProperty("class", "card")
        c_layout = QVBoxLayout(card)

        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "ID", "Client", "Service", "FY", "Due Date", "Priority", "Status", "Readiness %"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        configure_modern_table(self.table)
        c_layout.addWidget(self.table)

        layout.addWidget(card)

    def refresh_data(self):
        engs = self.main_window.engagement_service.list_engagements()
        self.table.setRowCount(0)

        for idx, eng in enumerate(engs):
            self.table.insertRow(idx)
            self.table.setItem(idx, 0, QTableWidgetItem(f"ENG-{eng.engagement_id:04d}"))
            self.table.setItem(idx, 1, QTableWidgetItem(eng.client_name))
            self.table.setItem(idx, 2, QTableWidgetItem(eng.service_name))
            self.table.setItem(idx, 3, QTableWidgetItem(eng.financial_year))
            self.table.setItem(idx, 4, QTableWidgetItem(eng.due_date))
            self.table.setItem(idx, 5, QTableWidgetItem(eng.priority.value))

            status_item = QTableWidgetItem(eng.status.value)
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(idx, 6, status_item)

            summ = self.main_window.engagement_service.get_readiness(eng.engagement_id)
            read_item = QTableWidgetItem(f"{summ.readiness_percentage}%")
            read_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(idx, 7, read_item)

    def export_all_engagements(self):
        engs = self.main_window.engagement_service.list_engagements()
        if not engs:
            QMessageBox.information(self, "No Records", "There are no engagements to export.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Engagements Export", str(Path.home() / "Documents" / "Clientdesk_Engagements.xlsx"),
            "Excel Files (*.xlsx)"
        )
        if not file_path:
            return

        ReportExportService.export_engagements_to_excel(engs, Path(file_path))
        QMessageBox.information(self, "Export Successful", f"Engagements report exported successfully to:\n{file_path}")

    def export_active_checklist(self):
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.information(self, "Selection Required", "Please select an engagement row to export its checklist.")
            return

        row = selected_rows[0].row()
        eng_id_str = self.table.item(row, 0).text()
        eng_id = int(eng_id_str.replace("ENG-", ""))

        eng = self.main_window.engagement_repo.get_by_id(eng_id)
        items = self.main_window.engagement_repo.get_items(eng_id)

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Document Checklist", str(Path.home() / "Documents" / f"Checklist_{eng.client_name.replace(' ', '_')}.xlsx"),
            "Excel Files (*.xlsx)"
        )
        if not file_path:
            return

        ReportExportService.export_checklist_to_excel(eng, items, Path(file_path))
        QMessageBox.information(self, "Export Successful", f"Checklist exported successfully to:\n{file_path}")
