"""Client Master view with search, registration modal, editing, deletion, and masked identifier controls."""

import re
from typing import Optional
from src.clientdesk_ai.ui.qt_compat import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame, QDialog, QGridLayout,
    QComboBox, QMessageBox, Qt
)
from src.clientdesk_ai.domain.models import Client
from src.clientdesk_ai.security.crypto import mask_pan, mask_gstin, mask_aadhaar
from src.clientdesk_ai.ui.theme import configure_modern_table, STATUS_BADGE_STYLES


class ClientsView(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.show_masked = False  # Internal practice default: unmasked PAN & Aadhaar
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(18)

        # Header & Actions
        header_layout = QHBoxLayout()
        title_box = QVBoxLayout()
        title_lbl = QLabel("Client Master Repository")
        title_lbl.setStyleSheet("font-size: 20px; font-weight: 700; color: #0F172A;")
        sub_lbl = QLabel("Maintain verified client entities, tax identifiers, change records, and contact profiles.")
        sub_lbl.setStyleSheet("font-size: 13px; color: #64748B;")
        title_box.addWidget(title_lbl)
        title_box.addWidget(sub_lbl)
        header_layout.addLayout(title_box)
        header_layout.addStretch()

        btn_add = QPushButton("+ Register New Client")
        btn_add.setProperty("class", "btn-primary")
        btn_add.clicked.connect(self.open_add_client_dialog)

        btn_edit = QPushButton("✏️ Edit Client")
        btn_edit.setProperty("class", "btn-secondary")
        btn_edit.clicked.connect(self.open_edit_client_dialog)

        btn_delete = QPushButton("🗑️ Remove Client")
        btn_delete.setProperty("class", "btn-danger")
        btn_delete.clicked.connect(self.delete_selected_client)

        self.btn_toggle_mask = QPushButton("🔒 Mask Identifiers")
        self.btn_toggle_mask.setProperty("class", "btn-secondary")
        self.btn_toggle_mask.setToolTip("Toggle identifier masking (defaults to unmasked for internal company use)")
        self.btn_toggle_mask.clicked.connect(self.toggle_masking)

        header_layout.addWidget(btn_add)
        header_layout.addWidget(btn_edit)
        header_layout.addWidget(btn_delete)
        header_layout.addWidget(self.btn_toggle_mask)
        layout.addLayout(header_layout)

        # Search Bar Card
        search_card = QFrame()
        search_card.setProperty("class", "card")
        sc_layout = QHBoxLayout(search_card)
        sc_layout.setContentsMargins(12, 10, 12, 10)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search clients by code, legal name, trade name, PAN, or Aadhaar...")
        self.search_input.textChanged.connect(self.refresh_data)
        sc_layout.addWidget(self.search_input)

        btn_clear = QPushButton("Clear")
        btn_clear.setProperty("class", "btn-secondary")
        btn_clear.clicked.connect(lambda: self.search_input.clear())
        sc_layout.addWidget(btn_clear)
        layout.addWidget(search_card)

        # Table (8 Columns: PAN & Aadhaar unmasked for internal company use)
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Client Code", "Legal Name", "Trade Name", "Entity Type", "PAN", "Aadhaar", "GSTIN", "Status"
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(0, 95)
        self.table.setColumnWidth(3, 130)
        self.table.setColumnWidth(4, 115)
        self.table.setColumnWidth(5, 125)
        self.table.setColumnWidth(6, 155)
        self.table.setColumnWidth(7, 90)
        self.table.horizontalHeader().setMinimumSectionSize(65)
        configure_modern_table(self.table)
        self.table.cellDoubleClicked.connect(lambda r, c: self.open_edit_client_dialog())
        layout.addWidget(self.table)

    def toggle_masking(self):
        """Toggle privacy masking between unmasked (internal company use) and masked (presentation mode)."""
        self.show_masked = not self.show_masked
        if self.show_masked:
            self.btn_toggle_mask.setText("👁️ Show Full Identifiers")
            self.table.setHorizontalHeaderLabels([
                "Client Code", "Legal Name", "Trade Name", "Entity Type", "PAN (Masked)", "Aadhaar (Masked)", "GSTIN (Masked)", "Status"
            ])
        else:
            self.btn_toggle_mask.setText("🔒 Mask Identifiers")
            self.table.setHorizontalHeaderLabels([
                "Client Code", "Legal Name", "Trade Name", "Entity Type", "PAN", "Aadhaar", "GSTIN", "Status"
            ])
        self.refresh_data()

    def refresh_data(self):
        query = self.search_input.text()
        clients = self.main_window.client_service.search_clients(query)
        self.table.setRowCount(0)

        for idx, c in enumerate(clients):
            self.table.insertRow(idx)

            code_item = QTableWidgetItem(c.client_code)
            code_item.setData(Qt.ItemDataRole.UserRole, c.client_id)
            self.table.setItem(idx, 0, code_item)

            self.table.setItem(idx, 1, QTableWidgetItem(c.client_name))
            self.table.setItem(idx, 2, QTableWidgetItem(c.trade_name or "-"))
            self.table.setItem(idx, 3, QTableWidgetItem(c.entity_type))

            # Internal company view: unmasked by default
            if self.show_masked:
                pan_disp = mask_pan(c.pan) if c.pan else "-"
                aadhaar_disp = mask_aadhaar(getattr(c, "aadhaar", "")) if getattr(c, "aadhaar", "") else "-"
                gstin_disp = mask_gstin(c.gstin) if c.gstin else "-"
            else:
                pan_disp = c.pan or "-"
                aadhaar_disp = getattr(c, "aadhaar", "") or "-"
                gstin_disp = c.gstin or "-"

            self.table.setItem(idx, 4, QTableWidgetItem(pan_disp))
            self.table.setItem(idx, 5, QTableWidgetItem(aadhaar_disp))
            self.table.setItem(idx, 6, QTableWidgetItem(gstin_disp))

            status_item = QTableWidgetItem(c.status)
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(idx, 7, status_item)

    def get_selected_client_id(self) -> Optional[int]:
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            return None
        row = selected_rows[0].row()
        item = self.table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def open_add_client_dialog(self):
        dialog = ClientFormDialog(self.main_window, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh_data()
            self.main_window.dashboard_view.refresh_data()

    def open_edit_client_dialog(self):
        client_id = self.get_selected_client_id()
        if not client_id:
            QMessageBox.information(self, "Selection Required", "Please select a client from the table first.")
            return

        client = self.main_window.client_repo.get_by_id(client_id)
        if not client:
            return

        dialog = ClientFormDialog(self.main_window, existing_client=client, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh_data()
            self.main_window.dashboard_view.refresh_data()

    def delete_selected_client(self):
        client_id = self.get_selected_client_id()
        if not client_id:
            QMessageBox.information(self, "Selection Required", "Please select a client to remove.")
            return

        client = self.main_window.client_repo.get_by_id(client_id)
        if not client:
            return

        reply = QMessageBox.question(
            self,
            "Confirm Client Removal",
            f"Are you sure you want to remove client '{client.client_name}' ({client.client_code})?\n\n"
            "If this client has existing engagements, their status will be set to INACTIVE to preserve compliance audit trails.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            ok, msg = self.main_window.client_repo.delete(client_id)
            self.refresh_data()
            self.main_window.dashboard_view.refresh_data()
            QMessageBox.information(self, "Client Status", msg)


class ClientFormDialog(QDialog):
    """Modal dialog for registering or modifying client records."""

    def __init__(self, main_window, existing_client: Optional[Client] = None, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.existing_client = existing_client

        mode = "Edit" if existing_client else "Register New"
        self.setWindowTitle(f"{mode} Client Master Record")
        self.setMinimumWidth(520)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        grid = QGridLayout()
        grid.setSpacing(12)

        # Fields
        self.code_edit = QLineEdit()
        self.code_edit.setPlaceholderText("e.g. CLT-0001 (Unique)")

        code_box = QHBoxLayout()
        code_box.addWidget(self.code_edit, 1)
        self.btn_auto_code = QPushButton("⚡ Auto-Generate")
        self.btn_auto_code.setToolTip("Auto-generate next sequential client code (CLT-XXXX)")
        self.btn_auto_code.setProperty("class", "btn-secondary")
        self.btn_auto_code.setStyleSheet("padding: 4px 10px; font-size: 11px; font-weight: 600;")
        self.btn_auto_code.clicked.connect(self.auto_generate_code)
        code_box.addWidget(self.btn_auto_code)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Legal entity name")

        self.trade_edit = QLineEdit()
        self.trade_edit.setPlaceholderText("Trade / brand name (optional)")

        self.type_combo = QComboBox()
        self.type_combo.addItems([
            "Sole Proprietorship",
            "Partnership Firm",
            "Private Limited Company",
            "Limited Liability Partnership (LLP)",
            "Hindu Undivided Family (HUF)",
            "Trust / Society / AOP",
            "Individual"
        ])

        self.pan_edit = QLineEdit()
        self.pan_edit.setPlaceholderText("10-character PAN (e.g. ABCDE1234F)")

        self.aadhaar_edit = QLineEdit()
        self.aadhaar_edit.setPlaceholderText("12-digit Aadhaar number (e.g. 1234 5678 9012)")

        self.gstin_edit = QLineEdit()
        self.gstin_edit.setPlaceholderText("15-character GSTIN (optional)")

        self.email_edit = QLineEdit()
        self.email_edit.setPlaceholderText("contact@client.com")

        self.phone_edit = QLineEdit()
        self.phone_edit.setPlaceholderText("Mobile / WhatsApp number")

        self.status_combo = QComboBox()
        self.status_combo.addItems(["ACTIVE", "INACTIVE", "PROSPECT", "ARCHIVED"])

        grid.addWidget(QLabel("Client Code: *"), 0, 0)
        grid.addLayout(code_box, 0, 1)

        grid.addWidget(QLabel("Legal Name: *"), 1, 0)
        grid.addWidget(self.name_edit, 1, 1)

        grid.addWidget(QLabel("Trade Name:"), 2, 0)
        grid.addWidget(self.trade_edit, 2, 1)

        grid.addWidget(QLabel("Entity Type: *"), 3, 0)
        grid.addWidget(self.type_combo, 3, 1)

        grid.addWidget(QLabel("PAN:"), 4, 0)
        grid.addWidget(self.pan_edit, 4, 1)

        grid.addWidget(QLabel("Aadhaar:"), 5, 0)
        grid.addWidget(self.aadhaar_edit, 5, 1)

        grid.addWidget(QLabel("GSTIN:"), 6, 0)
        grid.addWidget(self.gstin_edit, 6, 1)

        grid.addWidget(QLabel("Email:"), 7, 0)
        grid.addWidget(self.email_edit, 7, 1)

        grid.addWidget(QLabel("Phone / WhatsApp:"), 8, 0)
        grid.addWidget(self.phone_edit, 8, 1)

        grid.addWidget(QLabel("Status:"), 9, 0)
        grid.addWidget(self.status_combo, 9, 1)

        layout.addLayout(grid)

        # Pre-fill if editing
        if self.existing_client:
            self.code_edit.setText(self.existing_client.client_code)
            self.code_edit.setEnabled(False)  # Immutable primary business code
            self.btn_auto_code.setVisible(False)
            self.name_edit.setText(self.existing_client.client_name)
            self.trade_edit.setText(self.existing_client.trade_name)
            idx = self.type_combo.findText(self.existing_client.entity_type)
            if idx >= 0:
                self.type_combo.setCurrentIndex(idx)
            self.pan_edit.setText(self.existing_client.pan)
            self.aadhaar_edit.setText(getattr(self.existing_client, "aadhaar", ""))
            self.gstin_edit.setText(self.existing_client.gstin)
            self.email_edit.setText(self.existing_client.email)
            self.phone_edit.setText(self.existing_client.phone)
            s_idx = self.status_combo.findText(self.existing_client.status)
            if s_idx >= 0:
                self.status_combo.setCurrentIndex(s_idx)
        else:
            self.auto_generate_code()

        btn_box = QHBoxLayout()
        btn_box.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setProperty("class", "btn-secondary")
        btn_cancel.clicked.connect(self.reject)

        save_btn_text = "Save Changes" if self.existing_client else "Register Client"
        btn_save = QPushButton(save_btn_text)
        btn_save.setProperty("class", "btn-primary")
        btn_save.clicked.connect(self.save_client)

        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(btn_save)
        layout.addLayout(btn_box)

    def auto_generate_code(self):
        """Auto-populate the client code field with the next sequential code."""
        try:
            repo = getattr(self.main_window, "client_repo", None)
            if repo and hasattr(repo, "generate_next_client_code"):
                next_code = repo.generate_next_client_code()
                self.code_edit.setText(next_code)
        except Exception:
            pass

    def save_client(self):
        code = self.code_edit.text().strip().upper()
        name = self.name_edit.text().strip()
        entity_type = self.type_combo.currentText()
        pan = self.pan_edit.text().strip().upper()
        raw_aadhaar = self.aadhaar_edit.text().strip()
        clean_aadhaar = re.sub(r'[\s\-]', '', raw_aadhaar)
        gstin = self.gstin_edit.text().strip().upper()

        if not code or not name:
            QMessageBox.warning(self, "Validation Error", "Client Code and Legal Name are mandatory fields.")
            return

        # 1. PAN validation: Optional, but if entered must be 5 letters + 4 digits + 1 letter
        if pan:
            if not re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]$', pan):
                QMessageBox.warning(
                    self, "Validation Error",
                    f"Invalid PAN format: '{pan}'.\n\n"
                    "PAN is optional, but if entered must be 10 characters following the statutory format:\n"
                    "• First 5 characters must be Letters (A-Z)\n"
                    "• Next 4 characters must be Digits (0-9)\n"
                    "• Last character must be a Letter (A-Z)\n\n"
                    "Example: ABCDE1234F"
                )
                self.pan_edit.setFocus()
                return

        # 2. Aadhaar validation: Optional, but if entered must be exactly 12 numerical digits
        if clean_aadhaar:
            if not re.match(r'^[0-9]{12}$', clean_aadhaar):
                QMessageBox.warning(
                    self, "Validation Error",
                    f"Invalid Aadhaar format: '{raw_aadhaar}'.\n\n"
                    "Aadhaar is optional, but if entered must be exactly 12 numerical digits.\n"
                    "Example: 1234 5678 9012"
                )
                self.aadhaar_edit.setFocus()
                return

        # 3. GSTIN validation: Optional, but if entered must be 15 alphanumeric characters
        if gstin:
            if not re.match(r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$', gstin):
                QMessageBox.warning(
                    self, "Validation Error",
                    f"Invalid GSTIN format: '{gstin}'.\n\n"
                    "GSTIN is optional, but if entered must be 15 alphanumeric characters following the statutory format:\n"
                    "• 2-digit state code (01-38)\n"
                    "• 10-character PAN\n"
                    "• 1 entity registration number\n"
                    "• Default letter 'Z'\n"
                    "• 1 check digit\n\n"
                    "Example: 27ABCDE1234F1Z5"
                )
                self.gstin_edit.setFocus()
                return

            if pan and gstin[2:12] != pan:
                QMessageBox.warning(
                    self, "Validation Error",
                    f"GSTIN '{gstin}' does not match entered PAN '{pan}'.\n\n"
                    f"Characters 3-12 of GSTIN ('{gstin[2:12]}') must be identical to the client's PAN."
                )
                self.gstin_edit.setFocus()
                return

        actor = getattr(self.main_window, "current_user", None)

        if self.existing_client:
            updated = Client(
                client_id=self.existing_client.client_id,
                client_code=code,
                client_name=name,
                trade_name=self.trade_edit.text().strip(),
                entity_type=entity_type,
                pan=pan,
                aadhaar=clean_aadhaar,
                gstin=gstin,
                email=self.email_edit.text().strip(),
                phone=self.phone_edit.text().strip(),
                status=self.status_combo.currentText(),
                created_by=self.existing_client.created_by
            )
            ok, msg = self.main_window.client_service.update_client(updated, actor=actor)
            if not ok:
                QMessageBox.warning(self, "Update Error", msg)
                return
            QMessageBox.information(self, "Updated", msg)
            self.accept()
        else:
            client = Client(
                client_code=code,
                client_name=name,
                trade_name=self.trade_edit.text().strip(),
                entity_type=entity_type,
                pan=pan,
                aadhaar=clean_aadhaar,
                gstin=gstin,
                email=self.email_edit.text().strip(),
                phone=self.phone_edit.text().strip(),
                status=self.status_combo.currentText(),
                created_by=actor.user_id if actor else 1
            )
            ok, created_client, msg = self.main_window.client_service.register_client(client, actor=actor)
            if not ok:
                QMessageBox.warning(self, "Registration Error", msg)
                return
            QMessageBox.information(self, "Success", f"Client '{name}' successfully registered.")
            self.accept()
