"""Service Template Library view with dynamic Service & Checklist management, and KPI summaries."""

import sqlite3
from typing import List, Optional
from src.clientdesk_ai.ui.qt_compat import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QFrame, QSplitter, QDialog, QGridLayout,
    QLineEdit, QTextEdit, QComboBox, QMessageBox, Qt
)
from src.clientdesk_ai.domain.models import ServiceTemplate, ChecklistItem, RequirementType, UserRole
from src.clientdesk_ai.ui.theme import configure_modern_table, STATUS_BADGE_STYLES


class AddServiceDialog(QDialog):
    """Modal dialog to register new statutory services and service groups dynamically."""

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.created_service_id: Optional[int] = None

        self.setWindowTitle("Add New Service Template")
        self.resize(540, 420)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        desc = QLabel("Define a new statutory compliance service and master checklist group:")
        desc.setStyleSheet("color: #64748B; font-size: 12.5px;")
        layout.addWidget(desc)

        form_layout = QGridLayout()
        form_layout.setVerticalSpacing(12)
        form_layout.setHorizontalSpacing(12)

        # 1. Service Code
        form_layout.addWidget(QLabel("<b>Service Code: *</b>"), 0, 0)
        self.code_edit = QLineEdit()
        self.code_edit.setPlaceholderText("e.g. TDS_RET, PF_ESI_COMPL, FEMA_FLA")
        form_layout.addWidget(self.code_edit, 0, 1)

        # 2. Service Name
        form_layout.addWidget(QLabel("<b>Service Name: *</b>"), 1, 0)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. TDS Quarterly Return (Form 24Q / 26Q)")
        form_layout.addWidget(self.name_edit, 1, 1)

        # 3. Service Group
        form_layout.addWidget(QLabel("<b>Service Group: *</b>"), 2, 0)
        self.group_combo = QComboBox()
        self.group_combo.setEditable(True)

        # Populate from existing groups in database + standard defaults
        default_groups = [
            "GST", "ITR", "Company Formation", "Partnership Registration",
            "LLP Incorporation", "MCA Annual Compliance", "Other Compliance"
        ]
        existing_groups: List[str] = []
        try:
            existing_groups = self.main_window.template_repo.list_service_groups()
        except Exception:
            pass

        # Combine while preserving order and uniqueness
        all_groups: List[str] = []
        for g in existing_groups + default_groups:
            if g and g not in all_groups:
                all_groups.append(g)

        for g in all_groups:
            self.group_combo.addItem(g)

        form_layout.addWidget(self.group_combo, 2, 1)

        # 4. Description
        form_layout.addWidget(QLabel("Description:"), 3, 0, Qt.AlignmentFlag.AlignTop)
        self.desc_edit = QTextEdit()
        self.desc_edit.setPlaceholderText("Optional description of procedural scope, regulatory authority, and filing timelines...")
        self.desc_edit.setFixedHeight(90)
        form_layout.addWidget(self.desc_edit, 3, 1)

        layout.addLayout(form_layout)

        # Bottom Buttons
        btn_box = QHBoxLayout()
        btn_box.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setProperty("class", "btn-secondary")
        btn_cancel.setMinimumHeight(36)
        btn_cancel.clicked.connect(self.reject)

        btn_save = QPushButton("Save Service")
        btn_save.setProperty("class", "btn-primary")
        btn_save.setMinimumHeight(36)
        btn_save.clicked.connect(self.save_service)

        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(btn_save)
        layout.addLayout(btn_box)

    def save_service(self):
        code = self.code_edit.text().strip().upper()
        name = self.name_edit.text().strip()
        group = self.group_combo.currentText().strip()
        desc = self.desc_edit.toPlainText().strip()

        if not code:
            QMessageBox.warning(self, "Validation Error", "Service Code is mandatory (e.g. TDS_RET).")
            self.code_edit.setFocus()
            return

        if not name:
            QMessageBox.warning(self, "Validation Error", "Service Name is mandatory.")
            self.name_edit.setFocus()
            return

        if not group:
            QMessageBox.warning(self, "Validation Error", "Please specify a Service Group.")
            self.group_combo.setFocus()
            return

        try:
            new_id = self.main_window.template_repo.create_service(
                service_code=code,
                service_name=name,
                service_group=group,
                description=desc
            )
            self.created_service_id = new_id
            QMessageBox.information(self, "Service Created", f"Successfully registered service template '{name}' [{code}].")
            self.accept()
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, "Duplicate Code", f"A service with code '{code}' already exists in the system.")
        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Could not create service template:\n{e}")


class TemplatesView(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.selected_service_id = None
        self._all_services: List[ServiceTemplate] = []
        self.init_ui()

    def check_manage_permission(self) -> bool:
        """Only ADMIN and PARTNER roles can add new statutory services."""
        user = getattr(self.main_window, "current_user", None)
        if not user:
            return False
        role_val = user.role.value if hasattr(user.role, "value") else str(user.role)
        return role_val in (UserRole.ADMIN.value, UserRole.PARTNER.value, "ADMIN", "PARTNER")

    def create_kpi_card(self, title: str, value: str, accent_color: str) -> QFrame:
        card = QFrame()
        card.setProperty("class", "card")
        card.setFixedHeight(54)
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(12, 4, 12, 4)
        c_layout.setSpacing(1)

        t_lbl = QLabel(title)
        t_lbl.setStyleSheet("font-size: 10px; font-weight: 600; color: #64748B; letter-spacing: 0.5px;")
        v_lbl = QLabel(value)
        v_lbl.setObjectName("kpi_value")
        v_lbl.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {accent_color};")

        c_layout.addWidget(t_lbl)
        c_layout.addWidget(v_lbl)
        return card

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 14, 24, 14)
        layout.setSpacing(10)

        # 1. Header with "+ Add New Service" next to title
        header_layout = QHBoxLayout()
        title_box = QVBoxLayout()
        title_lbl = QLabel("Service Catalogue & Template Library")
        title_lbl.setStyleSheet("font-size: 18px; font-weight: 700; color: #0F172A;")
        sub_lbl = QLabel("Manage statutory service templates, business entity variants, and master document checklist requirements.")
        sub_lbl.setStyleSheet("font-size: 12.5px; color: #64748B;")
        title_box.addWidget(title_lbl)
        title_box.addWidget(sub_lbl)
        header_layout.addLayout(title_box)
        header_layout.addStretch()

        self.btn_add_service = QPushButton("+ Add New Service")
        self.btn_add_service.setProperty("class", "btn-primary")
        self.btn_add_service.setMinimumHeight(32)
        self.btn_add_service.clicked.connect(self.open_add_service_dialog)
        header_layout.addWidget(self.btn_add_service)

        btn_reload = QPushButton("🔄 Reload Catalogue")
        btn_reload.setProperty("class", "btn-secondary")
        btn_reload.setMinimumHeight(32)
        btn_reload.clicked.connect(self.refresh_data)
        header_layout.addWidget(btn_reload)
        layout.addLayout(header_layout)

        # 2. Catalogue KPI Metric Cards (utilizes top open area compactly)
        cards_grid = QGridLayout()
        cards_grid.setSpacing(10)

        self.card_groups = self.create_kpi_card("ACTIVE SERVICE GROUPS", "6", "#2563EB")
        self.card_templates = self.create_kpi_card("ACTIVE SERVICE TEMPLATES", "8", "#0D9488")
        self.card_items = self.create_kpi_card("MASTER CHECKLIST ITEMS", "0", "#4F46E5")
        self.card_variants = self.create_kpi_card("LEGAL ENTITY VARIANTS", "0", "#D97706")

        cards_grid.addWidget(self.card_groups, 0, 0)
        cards_grid.addWidget(self.card_templates, 0, 1)
        cards_grid.addWidget(self.card_items, 0, 2)
        cards_grid.addWidget(self.card_variants, 0, 3)
        layout.addLayout(cards_grid)

        # 3. Filter & Governance Toolbar Card
        filter_card = QFrame()
        filter_card.setProperty("class", "card")
        filter_card.setFixedHeight(46)
        fc_layout = QHBoxLayout(filter_card)
        fc_layout.setContentsMargins(12, 6, 12, 6)
        fc_layout.setSpacing(10)

        lbl_filter = QLabel("<b>Filter:</b>")
        lbl_filter.setStyleSheet("color: #0F172A; font-size: 12px;")
        fc_layout.addWidget(lbl_filter)

        self.group_combo = QComboBox()
        self.group_combo.setFixedHeight(28)
        self.group_combo.addItem("All Statutory Groups")
        self.group_combo.currentIndexChanged.connect(self.filter_services)
        fc_layout.addWidget(self.group_combo)

        self.search_edit = QLineEdit()
        self.search_edit.setFixedHeight(28)
        self.search_edit.setPlaceholderText("Filter templates by name, group, or code...")
        self.search_edit.textChanged.connect(self.filter_services)
        fc_layout.addWidget(self.search_edit)

        fc_layout.addStretch()

        scope_badge = QLabel("⚡ Dynamic Catalogue: Service expansion enabled for practice management")
        scope_badge.setFixedHeight(26)
        scope_badge.setStyleSheet(
            "color: #0369A1; font-size: 11px; font-weight: 600; background-color: #F0F9FF; "
            "border: 1px solid #BAE6FD; border-radius: 4px; padding: 3px 8px;"
        )
        fc_layout.addWidget(scope_badge)
        layout.addWidget(filter_card)

        # 4. Splitter: Services List on Left, Checklist Items on Right
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left Card: Services List
        left_card = QFrame()
        left_card.setProperty("class", "card")
        left_card.setMinimumWidth(340)
        left_card.setMaximumWidth(450)
        left_layout = QVBoxLayout(left_card)
        left_layout.setContentsMargins(12, 12, 12, 12)
        left_layout.setSpacing(8)

        self.s_title = QLabel("Approved Service Templates")
        self.s_title.setStyleSheet("font-size: 14px; font-weight: 600; color: #0F172A;")
        left_layout.addWidget(self.s_title)

        self.service_table = QTableWidget()
        self.service_table.setColumnCount(3)
        self.service_table.setHorizontalHeaderLabels(["Group", "Service Template", "Code"])
        self.service_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.service_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.service_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.service_table.setColumnWidth(0, 110)
        self.service_table.setColumnWidth(2, 95)
        configure_modern_table(self.service_table)
        self.service_table.itemSelectionChanged.connect(self.on_service_selected)
        left_layout.addWidget(self.service_table)

        splitter.addWidget(left_card)

        # Right Card: Items Table & Actions Toolbar
        right_card = QFrame()
        right_card.setProperty("class", "card")
        right_layout = QVBoxLayout(right_card)
        right_layout.setContentsMargins(16, 16, 16, 16)
        right_layout.setSpacing(12)

        # Right Card Header with Action Buttons
        items_hdr_layout = QHBoxLayout()
        self.items_title = QLabel("Checklist Document Items")
        self.items_title.setStyleSheet("font-size: 15px; font-weight: 700; color: #0F172A;")
        items_hdr_layout.addWidget(self.items_title)
        items_hdr_layout.addStretch()

        btn_add = QPushButton("+ Add Requirement")
        btn_add.setProperty("class", "btn-primary")
        btn_add.setStyleSheet("padding: 6px 12px; font-size: 12px;")
        btn_add.clicked.connect(self.open_add_item_dialog)

        btn_edit = QPushButton("✏️ Edit")
        btn_edit.setProperty("class", "btn-secondary")
        btn_edit.setStyleSheet("padding: 6px 12px; font-size: 12px;")
        btn_edit.clicked.connect(self.open_edit_item_dialog)

        btn_delete = QPushButton("🗑️ Remove")
        btn_delete.setProperty("class", "btn-danger")
        btn_delete.setStyleSheet("padding: 6px 12px; font-size: 12px;")
        btn_delete.clicked.connect(self.delete_selected_item)

        items_hdr_layout.addWidget(btn_add)
        items_hdr_layout.addWidget(btn_edit)
        items_hdr_layout.addWidget(btn_delete)
        right_layout.addLayout(items_hdr_layout)

        # Checklist Items Table
        self.items_table = QTableWidget()
        self.items_table.setColumnCount(5)
        self.items_table.setHorizontalHeaderLabels(["Category", "Document / Work Item Name", "Variants", "Requirement", "Guidance Note"])
        self.items_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.items_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.items_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.items_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.items_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.items_table.setColumnWidth(0, 120)
        self.items_table.setColumnWidth(2, 95)
        self.items_table.setColumnWidth(3, 130)
        configure_modern_table(self.items_table)
        self.items_table.cellDoubleClicked.connect(lambda r, c: self.open_edit_item_dialog())
        right_layout.addWidget(self.items_table)

        splitter.addWidget(right_card)
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([360, 740])
        layout.addWidget(splitter, 1)

    def refresh_data(self):
        # Security: Only Admin and Partner can add new services
        can_add = self.check_manage_permission()
        self.btn_add_service.setVisible(can_add)

        services = self.main_window.template_repo.list_services()
        self._all_services = services

        # Compute live KPI counts
        groups = set(s.service_group for s in services)
        total_items = 0
        total_variants = 0
        for s in services:
            try:
                total_items += len(self.main_window.template_repo.get_items(s.service_id, all_variants=True))
                total_variants += len(self.main_window.template_repo.list_variants(s.service_id))
            except Exception:
                pass

        self.card_groups.findChild(QLabel, "kpi_value").setText(str(len(groups)))
        self.card_templates.findChild(QLabel, "kpi_value").setText(str(len(services)))
        self.card_items.findChild(QLabel, "kpi_value").setText(str(total_items))
        self.card_variants.findChild(QLabel, "kpi_value").setText(str(total_variants))

        # Dynamically refresh group filter dropdown
        current_sel = self.group_combo.currentText()
        self.group_combo.blockSignals(True)
        self.group_combo.clear()
        self.group_combo.addItem("All Statutory Groups")
        for g in sorted(groups):
            self.group_combo.addItem(g)
        idx = self.group_combo.findText(current_sel)
        if idx >= 0:
            self.group_combo.setCurrentIndex(idx)
        else:
            self.group_combo.setCurrentIndex(0)
        self.group_combo.blockSignals(False)

        self.filter_services()

    def open_add_service_dialog(self):
        if not self.check_manage_permission():
            QMessageBox.warning(self, "Permission Denied", "Only ADMIN and PARTNER roles can add new statutory services.")
            return

        dialog = AddServiceDialog(self.main_window, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if dialog.created_service_id:
                self.selected_service_id = dialog.created_service_id
            self.refresh_data()

    def filter_services(self):
        selected_group = self.group_combo.currentText().strip()
        search_term = self.search_edit.text().strip().lower()

        filtered: List[ServiceTemplate] = []
        for s in self._all_services:
            # Group filtering
            if self.group_combo.currentIndex() > 0 and s.service_group != selected_group:
                continue

            # Search text filtering
            if search_term:
                match_text = f"{s.service_name} {s.service_code} {s.service_group}".lower()
                if search_term not in match_text:
                    continue

            filtered.append(s)

        self.service_table.setRowCount(0)
        self.s_title.setText(f"Approved Service Templates ({len(filtered)})")

        for idx, s in enumerate(filtered):
            self.service_table.insertRow(idx)

            grp_item = QTableWidgetItem(s.service_group)
            grp_item.setData(Qt.ItemDataRole.UserRole, s.service_id)
            self.service_table.setItem(idx, 0, grp_item)

            self.service_table.setItem(idx, 1, QTableWidgetItem(s.service_name))
            self.service_table.setItem(idx, 2, QTableWidgetItem(s.service_code))

        if filtered:
            matched = False
            if self.selected_service_id:
                for row in range(self.service_table.rowCount()):
                    item = self.service_table.item(row, 0)
                    if item and item.data(Qt.ItemDataRole.UserRole) == self.selected_service_id:
                        self.service_table.selectRow(row)
                        matched = True
                        break
            if not matched:
                self.service_table.selectRow(0)
        else:
            self.items_title.setText("No service templates match current filter.")
            self.items_table.setRowCount(0)
            self.selected_service_id = None

    def on_service_selected(self):
        selected_rows = self.service_table.selectionModel().selectedRows()
        if not selected_rows:
            return

        row = selected_rows[0].row()
        service_id = self.service_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        self.selected_service_id = service_id
        self.load_service_items(service_id)

    def load_service_items(self, service_id: int):
        service = self.main_window.template_repo.get_service(service_id)
        if not service:
            return

        self.items_title.setText(f"Checklist Requirements: {service.service_name} ({service.service_group})")
        variants = self.main_window.template_repo.list_variants(service_id)
        variant_map = {v.variant_id: v.variant_name for v in variants}
        items = self.main_window.template_repo.get_items(service_id, all_variants=True)

        self.items_table.setRowCount(0)
        for idx, itm in enumerate(items):
            self.items_table.insertRow(idx)
            self.items_table.setItem(idx, 0, QTableWidgetItem(itm.category_name))

            doc_item = QTableWidgetItem(itm.document_name)
            doc_item.setData(Qt.ItemDataRole.UserRole, itm.item_id)
            self.items_table.setItem(idx, 1, doc_item)

            variant_text = variant_map.get(itm.variant_id, "All") if itm.variant_id else "All"
            var_item = QTableWidgetItem(variant_text)
            var_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.items_table.setItem(idx, 2, var_item)

            req_item = QTableWidgetItem(itm.requirement_type.value)
            req_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.items_table.setItem(idx, 3, req_item)

            self.items_table.setItem(idx, 4, QTableWidgetItem(itm.guidance_note or "-"))

    def get_selected_item_id(self) -> Optional[int]:
        selected_rows = self.items_table.selectionModel().selectedRows()
        if not selected_rows:
            return None
        row = selected_rows[0].row()
        item = self.items_table.item(row, 1)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def open_add_item_dialog(self):
        if not self.selected_service_id:
            QMessageBox.information(self, "Selection Required", "Please select a service from the left list first.")
            return

        service = self.main_window.template_repo.get_service(self.selected_service_id)
        dialog = TemplateItemEditDialog(
            self.main_window,
            service_id=self.selected_service_id,
            service_name=service.service_name if service else "",
            parent=self
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh_data()
            self.load_service_items(self.selected_service_id)

    def open_edit_item_dialog(self):
        item_id = self.get_selected_item_id()
        if not item_id:
            QMessageBox.information(self, "Selection Required", "Please select a checklist item to edit.")
            return

        item = self.main_window.template_repo.get_item(item_id)
        if not item:
            return

        service = self.main_window.template_repo.get_service(item.service_id)
        dialog = TemplateItemEditDialog(
            self.main_window,
            service_id=item.service_id,
            service_name=service.service_name if service else "",
            existing_item=item,
            parent=self
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh_data()
            self.load_service_items(self.selected_service_id)

    def delete_selected_item(self):
        item_id = self.get_selected_item_id()
        if not item_id:
            QMessageBox.information(self, "Selection Required", "Please select a checklist item to remove.")
            return

        item = self.main_window.template_repo.get_item(item_id)
        if not item:
            return

        reply = QMessageBox.question(
            self,
            "Confirm Remove Item",
            f"Are you sure you want to remove '{item.document_name}' from the checklist template?\n\n"
            "This will affect newly created engagements under this service.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.main_window.template_repo.delete_item(item_id)
            self.refresh_data()
            self.load_service_items(self.selected_service_id)
            QMessageBox.information(self, "Item Removed", f"'{item.document_name}' was removed from the checklist template.")


class TemplateItemEditDialog(QDialog):
    """Modal dialog to add or edit a master checklist template requirement."""

    def __init__(self, main_window, service_id: int, service_name: str, existing_item: Optional[ChecklistItem] = None, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.service_id = service_id
        self.service_name = service_name
        self.existing_item = existing_item

        mode = "Edit" if existing_item else "Add"
        self.setWindowTitle(f"{mode} Checklist Requirement — {service_name}")
        self.resize(560, 480)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        header_lbl = QLabel(f"Service: <b>{self.service_name}</b>")
        header_lbl.setStyleSheet("font-size: 13px; color: #2563EB;")
        layout.addWidget(header_lbl)

        form_layout = QGridLayout()
        form_layout.setVerticalSpacing(10)
        form_layout.setHorizontalSpacing(12)

        # 1. Document / Requirement Name
        form_layout.addWidget(QLabel("Document / Item Name: *"), 0, 0)
        self.doc_name_edit = QLineEdit()
        self.doc_name_edit.setPlaceholderText("e.g. Electricity Bill of Premises, Form 16, Bank Certificate...")
        form_layout.addWidget(self.doc_name_edit, 0, 1)

        # 2. Category
        form_layout.addWidget(QLabel("Category:"), 1, 0)
        self.cat_combo = QComboBox()
        self.cat_combo.setEditable(True)
        common_categories = [
            "Identity Documents", "Address Proofs", "Bank Proofs",
            "Financial Statements", "Statutory Filings", "Registrations & Licenses",
            "Entity Constitutional Documents", "General Documents"
        ]
        self.cat_combo.addItems(common_categories)
        form_layout.addWidget(self.cat_combo, 1, 1)

        # 3. Variant Scope
        form_layout.addWidget(QLabel("Variant Scope:"), 2, 0)
        self.variant_combo = QComboBox()
        self.variant_combo.addItem("All Variants", None)
        variants = self.main_window.template_repo.list_variants(self.service_id)
        for v in variants:
            self.variant_combo.addItem(f"{v.variant_name} ({v.variant_code})", v.variant_id)
        form_layout.addWidget(self.variant_combo, 2, 1)

        # 4. Requirement Type
        form_layout.addWidget(QLabel("Requirement Type:"), 3, 0)
        self.req_combo = QComboBox()
        for rt in RequirementType:
            self.req_combo.addItem(rt.value, rt)
        form_layout.addWidget(self.req_combo, 3, 1)

        # 5. Allowed File Formats
        form_layout.addWidget(QLabel("Allowed File Formats:"), 4, 0)
        self.formats_edit = QLineEdit()
        self.formats_edit.setPlaceholderText("e.g. PDF, JPG, PNG")
        self.formats_edit.setText("PDF, JPG")
        form_layout.addWidget(self.formats_edit, 4, 1)

        # 6. Format Instructions
        form_layout.addWidget(QLabel("Format Instructions:"), 5, 0)
        self.format_instr_edit = QLineEdit()
        self.format_instr_edit.setPlaceholderText("e.g. Color scan, both sides, max 2 MB")
        form_layout.addWidget(self.format_instr_edit, 5, 1)

        # 7. Guidance Note
        form_layout.addWidget(QLabel("Guidance Note:"), 6, 0, Qt.AlignmentFlag.AlignTop)
        self.note_edit = QTextEdit()
        self.note_edit.setPlaceholderText("Instructions for client or verification guidelines (e.g. not older than 2 months, must be signed)...")
        self.note_edit.setMaximumHeight(85)
        form_layout.addWidget(self.note_edit, 6, 1)

        layout.addLayout(form_layout)

        # Pre-fill if editing
        if self.existing_item:
            self.doc_name_edit.setText(self.existing_item.document_name)
            idx = self.cat_combo.findText(self.existing_item.category_name)
            if idx >= 0:
                self.cat_combo.setCurrentIndex(idx)
            else:
                self.cat_combo.setEditText(self.existing_item.category_name)

            # Variant Scope pre-fill
            if self.existing_item.variant_id:
                for i in range(self.variant_combo.count()):
                    if self.variant_combo.itemData(i) == self.existing_item.variant_id:
                        self.variant_combo.setCurrentIndex(i)
                        break
            else:
                self.variant_combo.setCurrentIndex(0)

            for i in range(self.req_combo.count()):
                if self.req_combo.itemData(i) == self.existing_item.requirement_type:
                    self.req_combo.setCurrentIndex(i)
                    break

            self.formats_edit.setText(self.existing_item.file_formats or "PDF, JPG")
            self.format_instr_edit.setText(self.existing_item.format_instructions or "")
            self.note_edit.setText(self.existing_item.guidance_note)

        # Action Buttons
        btn_box = QHBoxLayout()
        btn_box.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setProperty("class", "btn-secondary")
        btn_cancel.clicked.connect(self.reject)

        btn_save = QPushButton("Save Requirement")
        btn_save.setProperty("class", "btn-primary")
        btn_save.clicked.connect(self.save_item)

        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(btn_save)
        layout.addLayout(btn_box)

    def save_item(self):
        doc_name = self.doc_name_edit.text().strip()
        if not doc_name:
            QMessageBox.warning(self, "Validation Error", "Document / Item Name is mandatory.")
            return

        category = self.cat_combo.currentText().strip() or "General Documents"
        variant_id = self.variant_combo.currentData()
        req_type = self.req_combo.currentData()
        file_formats = self.formats_edit.text().strip() or "PDF, JPG"
        format_instructions = self.format_instr_edit.text().strip()
        guidance = self.note_edit.toPlainText().strip()

        if self.existing_item:
            self.main_window.template_repo.update_item(
                item_id=self.existing_item.item_id,
                category_name=category,
                document_name=doc_name,
                requirement_type=req_type,
                guidance_note=guidance,
                variant_id=variant_id,
                file_formats=file_formats,
                format_instructions=format_instructions
            )
            QMessageBox.information(self, "Saved", f"Checklist requirement '{doc_name}' updated successfully.")
        else:
            self.main_window.template_repo.add_item(
                service_id=self.service_id,
                category_name=category,
                document_name=doc_name,
                requirement_type=req_type,
                guidance_note=guidance,
                variant_id=variant_id,
                file_formats=file_formats,
                format_instructions=format_instructions
            )
            QMessageBox.information(self, "Added", f"Checklist requirement '{doc_name}' added to template.")

        self.accept()
