"""Engagement and interactive checklist workspace with live readiness and document actions."""

import os
import sys
from pathlib import Path
from typing import List, Optional
from src.clientdesk_ai.ui.qt_compat import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QFrame, QSplitter, QProgressBar,
    QMessageBox, QFileDialog, QInputDialog, QComboBox, QDialog, QGridLayout,
    QLineEdit, QDateEdit, QDate, Qt, QMenu, QAction
)
from src.clientdesk_ai.ui.theme import STATUS_BADGE_STYLES, configure_modern_table, get_service_badge_style
from src.clientdesk_ai.intelligence.classifier import LocalServiceClassifier
from src.clientdesk_ai.domain.models import (
    Engagement, EngagementChecklistItem, DocumentStatus, RequirementType,
    ApplicabilityStatus, Priority, EngagementStatus, UserRole, AuditLog
)


class EngagementWorkspaceView(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.selected_engagement_id = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # Header
        header_layout = QHBoxLayout()
        title_box = QVBoxLayout()
        title_lbl = QLabel("Engagement & Checklist Workspace")
        title_lbl.setStyleSheet("font-size: 20px; font-weight: 700; color: #0F172A;")
        sub_lbl = QLabel("Track document collection, verify attachments, and manage compliance readiness.")
        sub_lbl.setStyleSheet("font-size: 13px; color: #64748B;")
        title_box.addWidget(title_lbl)
        title_box.addWidget(sub_lbl)
        header_layout.addLayout(title_box)
        header_layout.addStretch()

        btn_send_req = QPushButton("📤 Send Checklist to Client")
        btn_send_req.setProperty("class", "btn-secondary")
        btn_send_req.clicked.connect(self.open_send_requirements_dialog)
        header_layout.addWidget(btn_send_req)

        btn_new_eng = QPushButton("+ New Engagement")
        btn_new_eng.setProperty("class", "btn-primary")
        btn_new_eng.clicked.connect(self.open_new_engagement_dialog)
        header_layout.addWidget(btn_new_eng)
        layout.addLayout(header_layout)

        # Main Splitter: Left List, Right Checklist Workspace
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left Pane: Engagements Selector
        left_card = QFrame()
        left_card.setProperty("class", "card")
        left_card.setMinimumWidth(480)
        left_layout = QVBoxLayout(left_card)
        left_layout.setContentsMargins(10, 10, 10, 10)

        left_title = QLabel("Client Engagements")
        left_title.setStyleSheet("font-size: 14px; font-weight: 600; color: #0F172A; padding-bottom: 4px;")
        left_layout.addWidget(left_title)

        self.eng_table = QTableWidget()
        self.eng_table.setColumnCount(4)
        self.eng_table.setHorizontalHeaderLabels(["ID", "Client", "Service", "Status"])
        self.eng_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.eng_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.eng_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.eng_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.eng_table.setColumnWidth(0, 85)
        self.eng_table.setColumnWidth(1, 105)
        self.eng_table.setColumnWidth(3, 115)
        self.eng_table.horizontalHeader().setMinimumSectionSize(80)
        self.eng_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        configure_modern_table(self.eng_table)
        self.eng_table.itemSelectionChanged.connect(self.on_engagement_selected)
        self.eng_table.cellClicked.connect(lambda r, c: self.on_engagement_selected())
        left_layout.addWidget(self.eng_table)

        splitter.addWidget(left_card)

        # Right Pane: Active Checklist Workspace
        right_card = QFrame()
        right_card.setProperty("class", "card")
        right_layout = QVBoxLayout(right_card)
        right_layout.setContentsMargins(16, 16, 16, 16)
        right_layout.setSpacing(12)

        # Workspace Active Engagement Header
        self.active_eng_lbl = QLabel("Select an engagement from the list to open its checklist.")
        self.active_eng_lbl.setStyleSheet("font-size: 15px; font-weight: 700; color: #0F172A;")
        right_layout.addWidget(self.active_eng_lbl)

        # Progress / Readiness Bar
        prog_box = QVBoxLayout()
        p_hdr = QHBoxLayout()
        self.readiness_lbl = QLabel("Statutory Readiness: 0%")
        self.readiness_lbl.setStyleSheet("font-size: 12px; font-weight: 600; color: #0F172A;")
        self.collection_lbl = QLabel("Collection Progress: 0%")
        self.collection_lbl.setStyleSheet("font-size: 12px; font-weight: 500; color: #64748B;")
        p_hdr.addWidget(self.readiness_lbl)
        p_hdr.addStretch()
        p_hdr.addWidget(self.collection_lbl)
        prog_box.addLayout(p_hdr)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(12)
        prog_box.addWidget(self.progress_bar)
        right_layout.addLayout(prog_box)

        # Checklist Management Toolbar
        mgr_bar = QHBoxLayout()
        mgr_title = QLabel("Checklist of Work")
        mgr_title.setStyleSheet("font-size: 13px; font-weight: 700; color: #334155;")
        mgr_bar.addWidget(mgr_title)
        mgr_bar.addStretch()

        btn_add_eng_item = QPushButton("+ Add Work Item")
        btn_add_eng_item.setProperty("class", "btn-secondary")
        btn_add_eng_item.setStyleSheet("padding: 4px 10px; font-size: 11px; font-weight: 600; color: #2563EB;")
        btn_add_eng_item.clicked.connect(self.open_add_custom_item_dialog)

        btn_edit_eng_item = QPushButton("✏️ Edit Remarks")
        btn_edit_eng_item.setProperty("class", "btn-secondary")
        btn_edit_eng_item.setStyleSheet("padding: 4px 10px; font-size: 11px; font-weight: 600;")
        btn_edit_eng_item.clicked.connect(self.open_edit_custom_item_dialog)

        btn_toggle_scope = QPushButton("🚫 Remove / Restore (N/A)")
        btn_toggle_scope.setProperty("class", "btn-secondary")
        btn_toggle_scope.setStyleSheet("padding: 4px 10px; font-size: 11px; font-weight: 600; color: #DC2626;")
        btn_toggle_scope.clicked.connect(self.toggle_item_scope)

        mgr_bar.addWidget(btn_add_eng_item)
        mgr_bar.addWidget(btn_edit_eng_item)
        mgr_bar.addWidget(btn_toggle_scope)
        right_layout.addLayout(mgr_bar)

        # Checklist Items Table
        self.items_table = QTableWidget()
        self.items_table.setColumnCount(8)
        self.items_table.setHorizontalHeaderLabels([
            "Document Item", "Category", "Requirement", "Status", "Attached File", "Received Date", "Remarks", "Guidance Note"
        ])
        self.items_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.items_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.items_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.items_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.items_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.items_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.items_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        self.items_table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        self.items_table.horizontalHeader().setMinimumSectionSize(80)
        self.items_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        configure_modern_table(self.items_table)
        self.items_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.items_table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        right_layout.addWidget(self.items_table)

        # Bottom Actions Toolbar (Clean, non-overcrowded layout with More Actions menu)
        btn_received = QPushButton("Mark Received")
        btn_received.setProperty("class", "btn-secondary")
        btn_received.clicked.connect(lambda: self.update_selected_item_status(DocumentStatus.RECEIVED))

        btn_verify = QPushButton("Verify & Accept")
        btn_verify.setProperty("class", "btn-success")
        btn_verify.clicked.connect(lambda: self.update_selected_item_status(DocumentStatus.ACCEPTED))

        btn_view_attached = QPushButton("📂 View Attached File")
        btn_view_attached.setProperty("class", "btn-secondary")
        btn_view_attached.setToolTip("View or open the uploaded supporting document for the selected item")
        btn_view_attached.clicked.connect(self.view_selected_item_file)

        btn_deficiency_fix = QPushButton("🚨 Request Deficiency Fix")
        btn_deficiency_fix.setProperty("class", "btn-danger")
        btn_deficiency_fix.clicked.connect(self.request_deficiency_fix)

        # Create 'More Actions ▾' dropdown button with QMenu for secondary operations
        self.btn_more_actions = QPushButton("More Actions ▾")
        self.btn_more_actions.setProperty("class", "btn-secondary")
        self.btn_more_actions.setStyleSheet(
            "QPushButton { font-weight: 600; padding: 6px 14px; background-color: #F1F5F9; color: #1E293B; border: 1.5px solid #CBD5E1; }"
            "QPushButton:hover { background-color: #E2E8F0; }"
        )

        more_menu = QMenu(self.btn_more_actions)
        more_menu.setStyleSheet(
            "QMenu { background-color: #FFFFFF; border: 1.5px solid #CBD5E1; border-radius: 6px; padding: 4px; }"
            "QMenu::item { padding: 6px 20px 6px 12px; font-size: 12.5px; color: #0F172A; border-radius: 4px; }"
            "QMenu::item:selected { background-color: #EFF6FF; color: #1D4ED8; font-weight: 600; }"
        )

        act_verify_all = QAction("✅ Accept All Received", self)
        act_verify_all.triggered.connect(self.accept_all_received_items)
        more_menu.addAction(act_verify_all)

        act_attach = QAction("📎 Attach File", self)
        act_attach.triggered.connect(self.attach_file_to_selected_item)
        more_menu.addAction(act_attach)

        act_deficiency = QAction("⚠️ Report Deficiency", self)
        act_deficiency.triggered.connect(self.report_deficiency_on_selected_item)
        more_menu.addAction(act_deficiency)

        act_waive = QAction("🚫 Waive Requirement", self)
        act_waive.triggered.connect(self.waive_selected_item)
        more_menu.addAction(act_waive)

        self.btn_more_actions.setMenu(more_menu)

        btn_send_req_bar = QPushButton("📤 Send Requirements")
        btn_send_req_bar.setProperty("class", "btn-secondary")
        btn_send_req_bar.setStyleSheet("font-weight: 600; color: #0284C7;")
        btn_send_req_bar.clicked.connect(self.open_send_requirements_dialog)

        self.btn_submit_review = QPushButton("Submit for Senior Review →")
        self.btn_submit_review.setProperty("class", "btn-primary")
        self.btn_submit_review.clicked.connect(self.submit_for_senior_review)

        self.btn_mark_completed = QPushButton("🏁 Mark as Completed & Filed")
        self.btn_mark_completed.setProperty("class", "btn-success")
        self.btn_mark_completed.setStyleSheet("background-color: #059669; color: white; font-weight: 700; padding: 6px 14px;")
        self.btn_mark_completed.setVisible(False)
        self.btn_mark_completed.clicked.connect(self.mark_engagement_completed)

        actions_bar = QHBoxLayout()
        actions_bar.setSpacing(8)
        actions_bar.addWidget(btn_received)
        actions_bar.addWidget(btn_verify)
        actions_bar.addWidget(btn_view_attached)
        actions_bar.addWidget(btn_deficiency_fix)
        actions_bar.addStretch()
        actions_bar.addWidget(self.btn_more_actions)
        actions_bar.addWidget(btn_send_req_bar)
        actions_bar.addWidget(self.btn_submit_review)
        actions_bar.addWidget(self.btn_mark_completed)

        right_layout.addLayout(actions_bar)

        splitter.addWidget(right_card)
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([480, 720])
        layout.addWidget(splitter, 1)

    def refresh_data(self):
        engagements = self.main_window.engagement_service.list_engagements()
        self.eng_table.setRowCount(0)

        for idx, eng in enumerate(engagements):
            self.eng_table.insertRow(idx)
            self.eng_table.setItem(idx, 0, QTableWidgetItem(f"ENG-{eng.engagement_id:04d}"))
            self.eng_table.setItem(idx, 1, QTableWidgetItem(eng.client_name))

            # Service badge chip
            svc_badge = QLabel(eng.service_name)
            svc_badge.setStyleSheet(get_service_badge_style(eng.service_name))
            svc_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            svc_badge.setMinimumWidth(110)
            badge_box = QWidget()
            badge_box.setStyleSheet("background: transparent;")
            bb_layout = QHBoxLayout(badge_box)
            bb_layout.setContentsMargins(4, 2, 4, 2)
            bb_layout.addWidget(svc_badge)
            self.eng_table.setItem(idx, 2, QTableWidgetItem(""))
            self.eng_table.setCellWidget(idx, 2, badge_box)

            s_text = eng.status.value.replace('_', ' ')
            s_item = QTableWidgetItem(s_text)
            s_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.eng_table.setItem(idx, 3, s_item)

        if engagements and self.selected_engagement_id is None:
            self.eng_table.selectRow(0)

    def select_engagement_by_id(self, engagement_id: int):
        self.refresh_data()
        target_str = f"ENG-{engagement_id:04d}"
        for row in range(self.eng_table.rowCount()):
            item = self.eng_table.item(row, 0)
            if item and item.text() == target_str:
                self.eng_table.selectRow(row)
                self.selected_engagement_id = engagement_id
                self.load_engagement_checklist(engagement_id)
                return
        if self.eng_table.rowCount() > 0:
            self.eng_table.selectRow(0)

    def open_send_requirements_dialog(self):
        if not self.selected_engagement_id:
            QMessageBox.information(self, "Selection Required", "Please select an engagement first.")
            return
        from src.clientdesk_ai.ui.views.send_requirements_dialog import SendRequirementsDialog
        dialog = SendRequirementsDialog(self.main_window, self.selected_engagement_id, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.load_engagement_checklist(self.selected_engagement_id)
            self.main_window.dashboard_view.refresh_data()

    def on_engagement_selected(self):
        selected_rows = self.eng_table.selectionModel().selectedRows()
        if not selected_rows:
            return

        row = selected_rows[0].row()
        eng_id_str = self.eng_table.item(row, 0).text()
        eng_id = int(eng_id_str.replace("ENG-", ""))
        self.selected_engagement_id = eng_id
        self.load_engagement_checklist(eng_id)

    def load_engagement_checklist(self, engagement_id: int):
        eng = self.main_window.engagement_repo.get_by_id(engagement_id)
        if not eng:
            return

        self.active_eng_lbl.setText(
            f"ENG-{eng.engagement_id:04d} — {eng.client_name} | {eng.service_name} ({eng.financial_year}) | Due: {eng.due_date}"
        )

        items = self.main_window.engagement_repo.get_items(engagement_id)
        summary = self.main_window.engagement_service.get_readiness(engagement_id)

        attachments_map = {}
        try:
            if hasattr(self.main_window, "attachment_service"):
                attachments_map = self.main_window.attachment_service.get_attachments_for_engagement(engagement_id)
        except Exception:
            pass

        self.progress_bar.setValue(int(summary.readiness_percentage))
        self.readiness_lbl.setText(f"Statutory Readiness: {summary.readiness_percentage}%")
        self.collection_lbl.setText(
            f"Collection: {summary.collection_percentage}% ({summary.mandatory_accepted}/{summary.mandatory_total} Mandatory Accepted)"
        )

        # Dynamic action buttons based on engagement compliance status
        if eng.status == EngagementStatus.APPROVED:
            self.btn_mark_completed.setVisible(True)
            self.btn_submit_review.setVisible(False)
        elif eng.status in (EngagementStatus.COMPLETED, EngagementStatus.CANCELLED):
            self.btn_mark_completed.setVisible(False)
            self.btn_submit_review.setVisible(False)
        elif eng.status in (EngagementStatus.SUBMITTED_FOR_REVIEW, EngagementStatus.UNDER_REVIEW):
            self.btn_mark_completed.setVisible(False)
            self.btn_submit_review.setVisible(False)
        else:
            self.btn_mark_completed.setVisible(False)
            self.btn_submit_review.setVisible(True)

        self.items_table.setRowCount(0)
        for idx, itm in enumerate(items):
            self.items_table.insertRow(idx)

            item_atts = attachments_map.get(itm.engagement_item_id, [])
            has_attachment = bool(item_atts)

            # Col 0: Document Item (Prefixed with 📎 if file uploaded)
            doc_label = f"📎 {itm.document_name_snapshot}" if has_attachment else itm.document_name_snapshot
            name_item = QTableWidgetItem(doc_label)
            name_item.setData(Qt.ItemDataRole.UserRole, itm.engagement_item_id)
            self.items_table.setItem(idx, 0, name_item)

            # Col 1: Category
            self.items_table.setItem(idx, 1, QTableWidgetItem(itm.category_name))

            # Col 2: Requirement Badge
            if itm.is_exempt:
                req_val = "EXEMPT"
                req_style = "background-color: #F1F5F9; color: #64748B; font-weight: 600; font-size: 11px; border-radius: 4px; padding: 2px 6px;"
            else:
                req_val = itm.requirement_snapshot.value
                req_style = STATUS_BADGE_STYLES.get(req_val, "background-color: #F1F5F9; color: #475569; font-weight: 600; font-size: 11px; border-radius: 4px; padding: 2px 6px;")

            req_badge = QLabel(req_val)
            req_badge.setStyleSheet(req_style)
            req_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            req_badge.setMinimumWidth(95)
            req_box = QWidget()
            req_box.setStyleSheet("background: transparent;")
            rb_layout = QHBoxLayout(req_box)
            rb_layout.setContentsMargins(4, 2, 4, 2)
            rb_layout.addWidget(req_badge)
            self.items_table.setItem(idx, 2, QTableWidgetItem(req_val))
            self.items_table.setCellWidget(idx, 2, req_box)

            # Col 3: Status Badge
            if itm.is_exempt:
                status_val = "NOT_APPLICABLE"
                status_display = "NOT APPLICABLE"
            else:
                status_val = itm.collection_status.value
                status_display = status_val.replace('_', ' ')

            status_style = STATUS_BADGE_STYLES.get(status_val, "background-color: #F1F5F9; color: #475569; font-weight: 600; font-size: 11px; border-radius: 4px; padding: 2px 6px;")
            status_badge = QLabel(status_display)
            status_badge.setStyleSheet(status_style)
            status_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            status_badge.setMinimumWidth(115)
            status_box = QWidget()
            status_box.setStyleSheet("background: transparent;")
            sb_layout = QHBoxLayout(status_box)
            sb_layout.setContentsMargins(4, 2, 4, 2)
            sb_layout.addWidget(status_badge)
            self.items_table.setItem(idx, 3, QTableWidgetItem(status_display))
            self.items_table.setCellWidget(idx, 3, status_box)

            # Col 4: Attached File (Prominent clickable green pill or subtle placeholder)
            if has_attachment:
                first_att = item_atts[0]
                size_kb = max(1, round(first_att.file_size_bytes / 1024))
                if len(item_atts) == 1:
                    btn_att = QPushButton(f"📎 {first_att.original_filename} ({size_kb} KB)")
                    btn_att.setToolTip(f"Attached: {first_att.original_filename}\nSize: {size_kb} KB\nClick to open document")
                else:
                    btn_att = QPushButton(f"📎 {len(item_atts)} Files ({first_att.original_filename})")
                    btn_att.setToolTip(f"{len(item_atts)} files attached. Click to view list.")

                btn_att.setStyleSheet(
                    "QPushButton {"
                    "   background-color: #ECFDF5;"
                    "   color: #047857;"
                    "   border: 1px solid #A7F3D0;"
                    "   border-radius: 4px;"
                    "   font-weight: 600;"
                    "   font-size: 11px;"
                    "   padding: 2px 8px;"
                    "   text-align: left;"
                    "}"
                    "QPushButton:hover {"
                    "   background-color: #D1FAE5;"
                    "   border-color: #34D399;"
                    "   color: #065F46;"
                    "}"
                )
                btn_att.setCursor(Qt.CursorShape.PointingHandCursor)
                btn_att.clicked.connect(lambda _, a=first_att, all_a=item_atts: self.open_attachment_file(a) if len(all_a) == 1 else self.show_attachments_list_dialog(all_a))

                att_box = QWidget()
                att_box.setStyleSheet("background: transparent;")
                ab_layout = QHBoxLayout(att_box)
                ab_layout.setContentsMargins(4, 2, 4, 2)
                ab_layout.addWidget(btn_att)
                self.items_table.setItem(idx, 4, QTableWidgetItem(""))
                self.items_table.setCellWidget(idx, 4, att_box)
            else:
                lbl_none = QLabel("— No File —")
                lbl_none.setStyleSheet("color: #94A3B8; font-size: 11px; font-style: italic;")
                lbl_none.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lbl_none.setToolTip("No file attached yet. Click 'Attach File' below to upload evidence.")
                none_box = QWidget()
                none_box.setStyleSheet("background: transparent;")
                nb_layout = QHBoxLayout(none_box)
                nb_layout.setContentsMargins(4, 2, 4, 2)
                nb_layout.addWidget(lbl_none)
                self.items_table.setItem(idx, 4, QTableWidgetItem(""))
                self.items_table.setCellWidget(idx, 4, none_box)

            # Col 5: Received Date
            self.items_table.setItem(idx, 5, QTableWidgetItem(itm.received_date or "-"))

            # Col 6: Remarks
            remarks = itm.waiver_reason or itm.deficiency_reason or itm.internal_remarks or "-"
            self.items_table.setItem(idx, 6, QTableWidgetItem(remarks))

            # Col 7: Guidance Note [?] Action Button
            btn_guidance = QPushButton("💡 [?]")
            btn_guidance.setProperty("class", "btn-table-secondary")
            btn_guidance.setToolTip(f"View procedural SOP guidance for '{itm.document_name_snapshot}'")
            btn_guidance.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_guidance.clicked.connect(lambda _, name=itm.document_name_snapshot: self.show_guidance_for_document(name))

            g_panel = QWidget()
            g_panel.setStyleSheet("background: transparent;")
            gp_layout = QHBoxLayout(g_panel)
            gp_layout.setContentsMargins(4, 2, 4, 2)
            gp_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            gp_layout.addWidget(btn_guidance)
            self.items_table.setItem(idx, 7, QTableWidgetItem(""))
            self.items_table.setCellWidget(idx, 7, g_panel)

    def show_guidance_for_document(self, doc_name: str):
        """Query knowledge_documents using document_name_snapshot and display SOP in a popup."""
        repo = getattr(self.main_window, "knowledge_repo", None) or self.main_window.log_repo
        match = repo.find_guidance(doc_name)
        if match:
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Procedural SOP & Statutory Guidance")
            msg_box.setText(f"<h3>{match['title']}</h3><p><b>Service Group:</b> {match['service_group']}</p><hr>")
            msg_box.setInformativeText(match["content"])
            msg_box.setIcon(QMessageBox.Icon.Information)
            msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
            msg_box.exec()
        else:
            QMessageBox.information(
                self,
                "No SOP Found",
                f"No specific SOP article found matching '<b>{doc_name}</b>'.\n\n"
                "You can add a procedural guideline for this document in the Firm Wiki / Knowledge Base."
            )

    def get_selected_item_ids(self) -> List[int]:
        """Collect all engagement_item_id values from Column 0's UserRole for selected rows."""
        if not self.items_table.selectionModel():
            return []
        selected_rows = self.items_table.selectionModel().selectedRows()
        item_ids = []
        for index in selected_rows:
            row = index.row()
            item = self.items_table.item(row, 0)
            if item:
                val = item.data(Qt.ItemDataRole.UserRole)
                if val is not None:
                    item_ids.append(val)
        return item_ids

    def get_selected_item_id(self) -> Optional[int]:
        """Backward-compatible helper returning the first selected item ID or None."""
        ids = self.get_selected_item_ids()
        if not ids:
            return None
        return ids[0]

    def update_selected_item_status(self, status: DocumentStatus):
        item_ids = self.get_selected_item_ids()
        if not item_ids:
            QMessageBox.warning(self, "Selection Required", "Please select at least one checklist item row.")
            return

        actor = self.main_window.current_user
        for item_id in item_ids:
            self.main_window.checklist_service.update_item_status(
                item_id, status, actor
            )

        QMessageBox.information(
            self,
            "Status Updated",
            f"Successfully updated {len(item_ids)} items to {status.value}"
        )
        self.load_engagement_checklist(self.selected_engagement_id)
        self.main_window.dashboard_view.refresh_data()

    def accept_all_received_items(self):
        if not self.selected_engagement_id:
            QMessageBox.information(self, "Selection Required", "Please select an engagement first.")
            return

        count = self.main_window.engagement_repo.accept_all_received(
            self.selected_engagement_id,
            self.main_window.current_user.user_id if self.main_window.current_user else 1
        )
        if count > 0:
            QMessageBox.information(self, "Verified & Accepted", f"{count} received document(s) verified and accepted for compliance.")
        else:
            QMessageBox.information(self, "No Items", "No pending 'Received' items to verify.")

        self.load_engagement_checklist(self.selected_engagement_id)
        self.main_window.dashboard_view.refresh_data()

    def attach_file_to_selected_item(self):
        item_ids = self.get_selected_item_ids()
        if not item_ids:
            QMessageBox.warning(self, "Selection Required", "Please select a checklist item row first.")
            return

        if len(item_ids) > 1:
            QMessageBox.warning(self, "Single Item Required", "Please select only ONE row to attach a specific file.")
            return

        item_id = item_ids[0]

        file_path, _ = QFileDialog.getOpenFileName(
            self, "Attach Document File", "", "All Supported Files (*.pdf *.png *.jpg *.jpeg *.zip *.docx *.xlsx);;All Files (*.*)"
        )
        if not file_path:
            return

        from pathlib import Path
        actor = self.main_window.current_user
        ok, att, msg = self.main_window.attachment_service.attach_file(
            Path(file_path), item_id, actor
        )
        if not ok:
            QMessageBox.warning(self, "Attachment Failed", msg)
            return

        # Mark item as RECEIVED if currently NOT_REQUESTED or REQUESTED
        items = self.main_window.engagement_repo.get_items(self.selected_engagement_id)
        current = next((i for i in items if i.engagement_item_id == item_id), None)
        if current and current.collection_status in (DocumentStatus.NOT_REQUESTED, DocumentStatus.REQUESTED):
            self.main_window.checklist_service.update_item_status(
                item_id, DocumentStatus.RECEIVED, actor, remarks=f"Attached: {Path(file_path).name}"
            )

        QMessageBox.information(self, "Attachment Uploaded", msg)
        self.load_engagement_checklist(self.selected_engagement_id)
        self.main_window.dashboard_view.refresh_data()

    def open_attachment_file(self, attachment):
        """Open an uploaded supporting attachment file using the system default application."""
        try:
            file_path = self.main_window.attachment_service.get_attachment_file_path(attachment)
            if not file_path.exists():
                QMessageBox.warning(
                    self,
                    "File Not Found",
                    f"The attached file could not be found at:\n{file_path}\n\nIt may have been moved or deleted."
                )
                return

            if sys.platform == "win32":
                os.startfile(str(file_path))
            elif sys.platform == "darwin":
                import subprocess
                subprocess.Popen(["open", str(file_path)])
            else:
                import subprocess
                subprocess.Popen(["xdg-open", str(file_path)])
        except Exception as e:
            QMessageBox.critical(self, "Error Opening File", f"Could not open file '{attachment.original_filename}':\n{e}")

    def show_attachments_list_dialog(self, attachments):
        """Display a list of multiple files attached to a single checklist item."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Attached Supporting Documents")
        dlg.setMinimumWidth(520)
        d_layout = QVBoxLayout(dlg)
        d_layout.setContentsMargins(16, 16, 16, 16)
        d_layout.setSpacing(12)

        lbl = QLabel(f"<b>{len(attachments)} Files Uploaded for this Requirement:</b>")
        lbl.setStyleSheet("font-size: 13px; color: #0F172A;")
        d_layout.addWidget(lbl)

        table = QTableWidget()
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(["Filename", "Size", "Action"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        table.setColumnWidth(1, 85)
        table.setColumnWidth(2, 95)
        table.setRowCount(len(attachments))
        configure_modern_table(table)

        for r, att in enumerate(attachments):
            table.setItem(r, 0, QTableWidgetItem(att.original_filename))
            size_kb = max(1, round(att.file_size_bytes / 1024))
            size_item = QTableWidgetItem(f"{size_kb} KB")
            size_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(r, 1, size_item)

            btn_open = QPushButton("Open")
            btn_open.setProperty("class", "btn-secondary")
            btn_open.clicked.connect(lambda _, a=att: self.open_attachment_file(a))
            table.setCellWidget(r, 2, btn_open)

        d_layout.addWidget(table)

        btn_close = QPushButton("Close")
        btn_close.setProperty("class", "btn-secondary")
        btn_close.clicked.connect(dlg.accept)
        d_layout.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignRight)
        dlg.exec()

    def view_selected_item_file(self):
        """Open or view the attachment(s) for the currently selected checklist item."""
        item_id = self.get_selected_item_id()
        if not item_id:
            return

        attachments = self.main_window.attachment_service.list_by_item(item_id)
        if not attachments:
            QMessageBox.information(
                self,
                "No Attachment",
                "No file has been uploaded for this checklist item yet.\n\n"
                "Click '📎 Attach File' to upload supporting evidence (PDF, JPG, PNG, etc.)."
            )
            return

        if len(attachments) == 1:
            self.open_attachment_file(attachments[0])
        else:
            self.show_attachments_list_dialog(attachments)

    def report_deficiency_on_selected_item(self):
        item_ids = self.get_selected_item_ids()
        if not item_ids:
            QMessageBox.warning(self, "Selection Required", "Please select at least one checklist item row.")
            return

        reason, ok = QInputDialog.getText(
            self, "Report Document Deficiency",
            "Enter reason for deficiency (e.g. illegible scan, missing pages, wrong assessment year):"
        )
        if ok and reason.strip():
            actor = self.main_window.current_user
            def_reason = reason.strip()
            for item_id in item_ids:
                self.main_window.checklist_service.update_item_status(
                    item_id, DocumentStatus.DEFICIENT, actor, deficiency_reason=def_reason
                )
            self.load_engagement_checklist(self.selected_engagement_id)
            self.main_window.dashboard_view.refresh_data()
            QMessageBox.information(
                self, "Deficiencies Reported", f"Successfully marked {len(item_ids)} item(s) as DEFICIENT:\n{def_reason}"
            )

    def waive_selected_item(self):
        item_ids = self.get_selected_item_ids()
        if not item_ids:
            QMessageBox.warning(self, "Selection Required", "Please select at least one checklist item row.")
            return

        reason, ok = QInputDialog.getText(
            self, "Waive Requirement with Approval",
            "Enter statutory waiver justification (e.g. exempt entity, threshold not reached, partner approval):"
        )
        if ok and reason.strip():
            actor = self.main_window.current_user
            waiver_reason = reason.strip()
            for item_id in item_ids:
                self.main_window.checklist_service.update_item_status(
                    item_id, DocumentStatus.WAIVED_WITH_APPROVAL, actor, waiver_reason=waiver_reason
                )
            self.load_engagement_checklist(self.selected_engagement_id)
            self.main_window.dashboard_view.refresh_data()
            QMessageBox.information(
                self, "Requirements Waived", f"Successfully waived {len(item_ids)} requirement(s) with justification:\n{waiver_reason}"
            )

    def request_deficiency_fix(self):
        """Open a pre-filled message dialog to notify client of a deficient document."""
        item_id = self.get_selected_item_id()
        if not item_id:
            QMessageBox.information(self, "No Selection", "Please select a checklist item first.")
            return

        if not self.selected_engagement_id:
            return

        items = self.main_window.engagement_repo.get_items(self.selected_engagement_id)
        current = next((i for i in items if i.engagement_item_id == item_id), None)
        if not current:
            return

        if current.collection_status != DocumentStatus.DEFICIENT:
            QMessageBox.information(
                self, "Not Deficient",
                "Please select an item that is marked as DEFICIENT to send a correction request."
            )
            return

        eng = self.main_window.engagement_repo.get_by_id(self.selected_engagement_id)
        client = self.main_window.client_repo.get_by_id(eng.client_id) if eng else None
        client_name = client.client_name if client else "Client"
        client_email = client.email if client else ""
        deficiency_reason = current.deficiency_reason or "the document did not meet our requirements"

        dialog = DeficiencyFixDialog(
            main_window=self.main_window,
            client_name=client_name,
            client_email=client_email,
            doc_name=current.document_name_snapshot,
            deficiency_reason=deficiency_reason,
            parent=self
        )
        dialog.exec()

    def submit_for_senior_review(self):
        if not self.selected_engagement_id:
            return

        summary = self.main_window.engagement_service.get_readiness(self.selected_engagement_id)
        if not summary.is_ready_for_review:
            # Check if all pending blockers are simply RECEIVED items that haven't been accepted yet
            items = self.main_window.engagement_repo.get_items(self.selected_engagement_id)
            received_unaccepted = [
                i for i in items
                if not i.is_exempt
                and i.collection_status == DocumentStatus.RECEIVED
                and i.requirement_snapshot in (RequirementType.MANDATORY, RequirementType.CONDITIONAL)
            ]
            has_deficiencies = any(i.collection_status == DocumentStatus.DEFICIENT for i in items)
            missing_items = [
                i for i in items
                if not i.is_exempt
                and i.collection_status not in (DocumentStatus.RECEIVED, DocumentStatus.ACCEPTED, DocumentStatus.WAIVED_WITH_APPROVAL)
                and i.requirement_snapshot in (RequirementType.MANDATORY, RequirementType.CONDITIONAL)
            ]

            if received_unaccepted and not has_deficiencies and not missing_items:
                reply = QMessageBox.question(
                    self,
                    "Verify & Submit for Review",
                    f"All required documents have been received from the client (Collection: 100%).\n\n"
                    f"{len(received_unaccepted)} document(s) are currently marked as 'Received'. "
                    "Would you like to verify and accept all received items now to submit for Senior Review?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self.main_window.engagement_repo.accept_all_received(
                        self.selected_engagement_id,
                        self.main_window.current_user.user_id if self.main_window.current_user else 1
                    )
                else:
                    return
            else:
                blocker_msg = "\n• " + "\n• ".join(summary.blocking_reasons) if summary.blocking_reasons else "Mandatory items not satisfied."
                QMessageBox.warning(
                    self,
                    "Readiness Gate Blocked",
                    f"Cannot submit for review until 100% of mandatory requirements are accepted or waived:\n{blocker_msg}\n\n"
                    "Tip: If an item is not required for this client, select it and click '🚫 Remove / Restore (N/A)' to exclude it from the requirement."
                )
                return

        ok, msg = self.main_window.engagement_service.submit_for_review(
            self.selected_engagement_id, self.main_window.current_user
        )
        if not ok:
            QMessageBox.warning(self, "Readiness Gate Blocked", msg)
            return

        QMessageBox.information(self, "Submitted", msg)
        self.refresh_data()
        self.load_engagement_checklist(self.selected_engagement_id)
        self.main_window.dashboard_view.refresh_data()

    def mark_engagement_completed(self):
        """Mark an approved engagement as COMPLETED and filed on the statutory portal."""
        if not self.selected_engagement_id:
            return
        eng = self.main_window.engagement_repo.get_by_id(self.selected_engagement_id)
        if not eng:
            return

        reply = QMessageBox.question(
            self,
            "Confirm Statutory Filing & Completion",
            f"Mark ENG-{eng.engagement_id:04d} ({eng.service_name}) as Completed & Filed?\n\n"
            "This confirms that:\n"
            "1. All approved compliance deliverables and returns have been filed on the official statutory portal.\n"
            "2. Statutory acknowledgment / receipt (ITR-V, GSTR-3B ARN, MCA SRN) has been dispatched to the client.\n"
            "3. The engagement file is officially closed, achieving 100% statutory readiness and archived into the permanent audit trail.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        if reply == QMessageBox.StandardButton.Yes:
            user = self.main_window.current_user
            user_id = user.user_id if user else 1
            user_name = user.full_name or user.username if user else "System"
            self.main_window.engagement_repo.update_status(
                self.selected_engagement_id,
                EngagementStatus.COMPLETED,
                user_id,
                "Filing completed on statutory portal and client deliverable dispatched."
            )
            self.main_window.log_repo.add_audit(
                AuditLog(
                    actor_id=user_id,
                    actor_username=user.username if user else "admin",
                    event_type="ENGAGEMENT_COMPLETED",
                    target_entity="ENGAGEMENT",
                    target_id=str(self.selected_engagement_id),
                    details=f"Engagement ENG-{eng.engagement_id:04d} closed and marked completed by {user_name}."
                )
            )
            QMessageBox.information(
                self, "Engagement Completed",
                f"Engagement ENG-{eng.engagement_id:04d} successfully marked as Completed & Filed!"
            )
            self.refresh_data()
            self.load_engagement_checklist(self.selected_engagement_id)
            if hasattr(self.main_window, "dashboard_view"):
                self.main_window.dashboard_view.refresh_data()

    def open_new_engagement_dialog(self):
        dialog = NewEngagementDialog(self.main_window, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh_data()

    def open_add_custom_item_dialog(self):
        if not self.selected_engagement_id:
            QMessageBox.information(self, "Selection Required", "Please select an engagement first.")
            return

        dialog = AddCustomChecklistItemDialog(self.main_window, self.selected_engagement_id, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.load_engagement_checklist(self.selected_engagement_id)
            self.main_window.dashboard_view.refresh_data()

    def open_edit_custom_item_dialog(self):
        item_id = self.get_selected_item_id()
        if not item_id:
            return

        items = self.main_window.engagement_repo.get_items(self.selected_engagement_id)
        current = next((i for i in items if i.engagement_item_id == item_id), None)
        if not current:
            return

        remarks, ok = QInputDialog.getText(
            self,
            "Edit Checklist Item Notes",
            f"Update remarks / guidelines for '{current.document_name_snapshot}':",
            QLineEdit.EchoMode.Normal,
            current.internal_remarks or ""
        )
        if ok:
            self.main_window.engagement_repo.update_item_remarks(item_id, remarks)
            self.load_engagement_checklist(self.selected_engagement_id)

    def toggle_item_scope(self):
        item_id = self.get_selected_item_id()
        if not item_id:
            return

        items = self.main_window.engagement_repo.get_items(self.selected_engagement_id)
        current = next((i for i in items if i.engagement_item_id == item_id), None)
        if not current:
            return

        if current.is_exempt:
            reply = QMessageBox.question(
                self,
                "Restore Requirement",
                f"Restore '{current.document_name_snapshot}' back to active statutory scope?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.main_window.engagement_repo.toggle_applicability(item_id, is_applicable=True)
                self.load_engagement_checklist(self.selected_engagement_id)
                self.main_window.dashboard_view.refresh_data()
        else:
            reason, ok = QInputDialog.getText(
                self,
                "Remove Requirement from Scope",
                f"Enter reason for marking '{current.document_name_snapshot}' as Not Applicable (N/A):\n"
                "(e.g. Entity exempt, client turnover below threshold, no branch office):"
            )
            if ok and reason.strip():
                self.main_window.engagement_repo.toggle_applicability(item_id, is_applicable=False, reason=reason.strip())
                self.load_engagement_checklist(self.selected_engagement_id)
                self.main_window.dashboard_view.refresh_data()
                QMessageBox.information(self, "Scope Updated", f"'{current.document_name_snapshot}' marked as Not Applicable and excluded from readiness calculation.")


class AddCustomChecklistItemDialog(QDialog):
    """Dialog to add a client-specific document requirement to an active engagement."""

    def __init__(self, main_window, engagement_id: int, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.engagement_id = engagement_id
        self.setWindowTitle("Add Client-Specific Checklist Item")
        self.resize(500, 320)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        desc_lbl = QLabel("Add an additional document or work requirement specific to this client engagement.")
        desc_lbl.setStyleSheet("font-size: 12px; color: #64748B;")
        layout.addWidget(desc_lbl)

        form = QGridLayout()
        form.setVerticalSpacing(10)

        form.addWidget(QLabel("Document / Item Name: *"), 0, 0)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. Factory Rent Agreement, Form 26AS, NOC from Landlord...")
        form.addWidget(self.name_edit, 0, 1)

        form.addWidget(QLabel("Category:"), 1, 0)
        self.cat_combo = QComboBox()
        self.cat_combo.setEditable(True)
        self.cat_combo.addItems([
            "Specific Client Documents", "Address Proofs", "Financial Statements",
            "Statutory Filings", "Identity Documents", "General Documents"
        ])
        form.addWidget(self.cat_combo, 1, 1)

        form.addWidget(QLabel("Requirement Type:"), 2, 0)
        self.req_combo = QComboBox()
        for rt in RequirementType:
            self.req_combo.addItem(rt.value, rt)
        form.addWidget(self.req_combo, 2, 1)

        form.addWidget(QLabel("Remarks / Instructions:"), 3, 0)
        self.remarks_edit = QLineEdit()
        self.remarks_edit.setPlaceholderText("Special notes for client or operator...")
        form.addWidget(self.remarks_edit, 3, 1)

        layout.addLayout(form)

        btn_box = QHBoxLayout()
        btn_box.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setProperty("class", "btn-secondary")
        btn_cancel.clicked.connect(self.reject)

        btn_save = QPushButton("Add to Checklist")
        btn_save.setProperty("class", "btn-primary")
        btn_save.clicked.connect(self.save_item)

        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(btn_save)
        layout.addLayout(btn_box)

    def save_item(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation Error", "Document / Item Name is mandatory.")
            return

        cat = self.cat_combo.currentText().strip() or "General Documents"
        req = self.req_combo.currentData()
        remarks = self.remarks_edit.text().strip()

        self.main_window.engagement_repo.add_custom_item(
            engagement_id=self.engagement_id,
            category_name=cat,
            document_name=name,
            requirement_type=req,
            internal_remarks=remarks
        )
        QMessageBox.information(self, "Item Added", f"'{name}' added to active engagement checklist.")
        self.accept()


class DeficiencyFixDialog(QDialog):
    """Dialog to notify a client about a deficient document and request a correction."""

    def __init__(self, main_window, client_name: str, client_email: str,
                 doc_name: str, deficiency_reason: str, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.client_email = client_email
        self.setWindowTitle("Request Deficiency Correction")
        self.resize(600, 380)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        desc = QLabel(f"Send a deficiency correction request to <b>{client_name}</b>:")
        desc.setStyleSheet("color: #64748B; font-size: 12px;")
        layout.addWidget(desc)

        from src.clientdesk_ai.ui.qt_compat import QTextEdit as _QTextEdit
        self.msg_edit = _QTextEdit()
        self.msg_edit.setStyleSheet(
            "font-family: Consolas, 'Segoe UI', monospace; font-size: 13px; "
            "background-color: #FFFFFF; border: 1.5px solid #CBD5E1; border-radius: 6px; padding: 8px;"
        )
        default_msg = (
            f"Dear {client_name},\n\n"
            f"The document '{doc_name}' you submitted was rejected because: {deficiency_reason}.\n\n"
            f"Please upload a clear, correct copy at your earliest convenience to avoid delays "
            f"in your compliance filing.\n\n"
            f"Thank you,\n"
            f"Clientdesk AI Compliance Team"
        )
        self.msg_edit.setPlainText(default_msg)
        layout.addWidget(self.msg_edit)

        btn_bar = QHBoxLayout()
        btn_copy_wa = QPushButton("📱 Copy for WhatsApp")
        btn_copy_wa.setProperty("class", "btn-secondary")
        btn_copy_wa.setMinimumHeight(36)
        btn_copy_wa.clicked.connect(self.copy_to_clipboard)

        btn_send_email = QPushButton("📧 Send via Email")
        btn_send_email.setProperty("class", "btn-primary")
        btn_send_email.setMinimumHeight(36)
        btn_send_email.clicked.connect(self.send_via_email)

        btn_close = QPushButton("Close")
        btn_close.setProperty("class", "btn-secondary")
        btn_close.setMinimumHeight(36)
        btn_close.clicked.connect(self.accept)

        btn_bar.addWidget(btn_copy_wa)
        btn_bar.addStretch()
        btn_bar.addWidget(btn_send_email)
        btn_bar.addWidget(btn_close)
        layout.addLayout(btn_bar)

    def copy_to_clipboard(self):
        from src.clientdesk_ai.ui.qt_compat import QApplication
        QApplication.clipboard().setText(self.msg_edit.toPlainText())
        QMessageBox.information(self, "Copied", "Message copied to clipboard!")

    def send_via_email(self):
        if not self.client_email or "@" not in self.client_email:
            QMessageBox.warning(
                self, "No Email",
                "Client does not have a valid email address saved in Master Records.\n"
                "Please update the client's email before sending via email."
            )
            return
        if not hasattr(self.main_window, "email_service") or not self.main_window.email_service:
            QMessageBox.critical(self, "Service Error", "Email service is not initialized.")
            return
        body = self.msg_edit.toPlainText()
        ok, msg = self.main_window.email_service.send_checklist_email(
            to_email=self.client_email,
            subject="Document Deficiency — Correction Required",
            body_text=body
        )
        if ok:
            QMessageBox.information(self, "Email Sent", "Deficiency correction request sent successfully.")
            self.accept()
        else:
            QMessageBox.critical(self, "Email Failed", f"Could not send email:\n{msg}")


class NewEngagementDialog(QDialog):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.setWindowTitle("Create New Client Engagement")
        self.setMinimumWidth(520)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # Smart Recommendation Bar
        rec_card = QFrame()
        rec_card.setStyleSheet("background-color: #F1F5F9; border-radius: 6px; padding: 10px;")
        rec_layout = QVBoxLayout(rec_card)
        rec_layout.setContentsMargins(8, 8, 8, 8)
        rec_layout.setSpacing(6)

        r_hdr = QLabel("<b>Offline Intelligence: Service Category Assistant</b>")
        r_hdr.setStyleSheet("color: #0F172A; font-size: 12px;")
        rec_layout.addWidget(r_hdr)

        r_input_box = QHBoxLayout()
        self.inquiry_edit = QLineEdit()
        self.inquiry_edit.setPlaceholderText("Describe client requirements (e.g. 'incorporate software startup with 2 directors')...")
        btn_recommend = QPushButton("Recommend Service")
        btn_recommend.setProperty("class", "btn-secondary")
        btn_recommend.clicked.connect(self.run_service_recommendation)
        r_input_box.addWidget(self.inquiry_edit)
        r_input_box.addWidget(btn_recommend)
        rec_layout.addLayout(r_input_box)

        self.recommend_lbl = QLabel("")
        self.recommend_lbl.setStyleSheet("font-size: 11px; color: #475569;")
        rec_layout.addWidget(self.recommend_lbl)

        layout.addWidget(rec_card)

        grid = QGridLayout()
        grid.setSpacing(12)

        # Clients Dropdown
        self.client_combo = QComboBox()
        clients = self.main_window.client_service.search_clients("")
        for c in clients:
            self.client_combo.addItem(f"{c.client_name} ({c.client_code})", c.client_id)

        # Service Templates Dropdown (Strictly 6 approved groups)
        self.service_combo = QComboBox()
        services = self.main_window.template_repo.list_services()
        for s in services:
            self.service_combo.addItem(f"[{s.service_group}] {s.service_name}", s.service_id)
        self.service_combo.currentIndexChanged.connect(self.on_service_changed)

        # GST Entity Variant Dropdown (if GST Registration selected)
        self.variant_combo = QComboBox()
        self.variant_combo.setVisible(False)
        self.variant_lbl = QLabel("GST Entity Constitution:")
        self.variant_lbl.setVisible(False)

        # Financial Year & Period
        self.fy_combo = QComboBox()
        self.fy_combo.addItems(["2026-2027", "2025-2026", "2024-2025"])

        self.period_combo = QComboBox()
        self.period_combo.addItems(["Annual", "Monthly", "Quarterly", "One-Time Assignment"])

        # Due Date
        self.due_edit = QDateEdit()
        self.due_edit.setDate(QDate.currentDate().addDays(30))
        self.due_edit.setCalendarPopup(True)

        # Priority
        self.priority_combo = QComboBox()
        self.priority_combo.addItems(["NORMAL", "HIGH", "URGENT"])

        # Assigned Staff & Reviewer
        self.staff_combo = QComboBox()
        self.reviewer_combo = QComboBox()
        users = self.main_window.user_repo.list_all()
        for u in users:
            self.staff_combo.addItem(f"{u.full_name} ({u.role.value})", u.user_id)
            if u.role in (UserRole.ADMIN, UserRole.PARTNER, UserRole.SENIOR):
                self.reviewer_combo.addItem(f"{u.full_name} ({u.role.value})", u.user_id)

        # Pre-select distinct defaults to respect the 4-Eyes Principle
        staff_users = [u for u in users if u.role == UserRole.STAFF]
        senior_users = [u for u in users if u.role in (UserRole.SENIOR, UserRole.PARTNER, UserRole.ADMIN)]
        if staff_users:
            s_idx = self.staff_combo.findData(staff_users[0].user_id)
            if s_idx >= 0:
                self.staff_combo.setCurrentIndex(s_idx)
        if senior_users:
            target_rev = senior_users[0]
            for s in senior_users:
                if staff_users and s.user_id != staff_users[0].user_id:
                    target_rev = s
                    break
            r_idx = self.reviewer_combo.findData(target_rev.user_id)
            if r_idx >= 0:
                self.reviewer_combo.setCurrentIndex(r_idx)

        grid.addWidget(QLabel("Select Client *:"), 0, 0)
        grid.addWidget(self.client_combo, 0, 1)

        grid.addWidget(QLabel("Approved Service Template *:"), 1, 0)
        grid.addWidget(self.service_combo, 1, 1)

        grid.addWidget(self.variant_lbl, 2, 0)
        grid.addWidget(self.variant_combo, 2, 1)

        grid.addWidget(QLabel("Financial Year:"), 3, 0)
        grid.addWidget(self.fy_combo, 3, 1)

        grid.addWidget(QLabel("Filing Period:"), 4, 0)
        grid.addWidget(self.period_combo, 4, 1)

        grid.addWidget(QLabel("Statutory Due Date *:"), 5, 0)
        grid.addWidget(self.due_edit, 5, 1)

        grid.addWidget(QLabel("Priority:"), 6, 0)
        grid.addWidget(self.priority_combo, 6, 1)

        grid.addWidget(QLabel("Assigned Operator (Staff):"), 7, 0)
        grid.addWidget(self.staff_combo, 7, 1)

        grid.addWidget(QLabel("Designated Senior Reviewer:"), 8, 0)
        grid.addWidget(self.reviewer_combo, 8, 1)

        layout.addLayout(grid)

        # Buttons
        btn_box = QHBoxLayout()
        btn_box.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setProperty("class", "btn-secondary")
        btn_cancel.clicked.connect(self.reject)

        btn_save = QPushButton("Initialize Engagement & Snapshot")
        btn_save.setProperty("class", "btn-primary")
        btn_save.clicked.connect(self.create_engagement)

        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(btn_save)
        layout.addLayout(btn_box)

        self.on_service_changed()

    def run_service_recommendation(self):
        text = self.inquiry_edit.text().strip()
        if not text:
            self.recommend_lbl.setText("Please enter client inquiry text to receive a recommendation.")
            return

        clf = LocalServiceClassifier()
        group, conf, expl = clf.predict(text)
        if not group:
            self.recommend_lbl.setText(f"<span style='color: #D97706;'>• {expl}</span>")
            return

        self.recommend_lbl.setText(f"<span style='color: #059669;'>• Suggested <b>{group}</b> ({conf*100:.1f}% confidence)</span>")

        # Auto-select the corresponding service in the dropdown
        for idx in range(self.service_combo.count()):
            txt = self.service_combo.itemText(idx)
            if f"[{group}]" in txt:
                self.service_combo.setCurrentIndex(idx)
                break

    def on_service_changed(self):
        s_id = self.service_combo.currentData()
        if not s_id:
            return
        service = self.main_window.template_repo.get_service(s_id)
        if service and service.service_code == "GST_REG":
            self.variant_lbl.setVisible(True)
            self.variant_combo.setVisible(True)
            self.variant_combo.clear()
            variants = self.main_window.template_repo.list_variants(s_id)
            for v in variants:
                self.variant_combo.addItem(f"{v.variant_name}", v.variant_id)
        else:
            self.variant_lbl.setVisible(False)
            self.variant_combo.setVisible(False)

    def create_engagement(self):
        client_id = self.client_combo.currentData()
        service_id = self.service_combo.currentData()
        variant_id = self.variant_combo.currentData() if self.variant_combo.isVisible() else None

        if not client_id or not service_id:
            QMessageBox.warning(self, "Validation Error", "Please select a client and service template.")
            return

        due_date = self.due_edit.date().toString("yyyy-MM-dd")
        assigned_to = self.staff_combo.currentData() or self.main_window.current_user.user_id
        reviewer_id = self.reviewer_combo.currentData() or self.main_window.current_user.user_id

        if assigned_to == reviewer_id:
            QMessageBox.warning(
                self, "4-Eyes Principle Requirement",
                "Assigned Operator (Staff) and Designated Senior Reviewer must be different people.\n\n"
                "Under the firm's quality policy (4-Eyes Principle), the operator who compiles the documents cannot sign off on their own work."
            )
            return

        eng = Engagement(
            client_id=client_id,
            service_id=service_id,
            variant_id=variant_id,
            financial_year=self.fy_combo.currentText(),
            tax_period=self.period_combo.currentText(),
            due_date=due_date,
            priority=Priority(self.priority_combo.currentText()),
            assigned_to=assigned_to,
            reviewer_id=reviewer_id
        )

        ok, eng_id, msg = self.main_window.engagement_service.create_engagement(eng, self.main_window.current_user)
        if not ok:
            QMessageBox.warning(self, "Creation Error", msg)
            return

        QMessageBox.information(self, "Success", msg)
        self.accept()
