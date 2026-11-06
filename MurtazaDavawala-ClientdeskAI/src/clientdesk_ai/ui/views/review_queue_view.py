"""Senior Review Queue with segregation of duties, review decision recording, and real-time KPI metrics."""

import os
import sys
from typing import List, Optional
from src.clientdesk_ai.ui.qt_compat import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QFrame, QSplitter, QTextEdit, QMessageBox,
    QGridLayout, QComboBox, QLineEdit, QDialog, Qt
)
from src.clientdesk_ai.domain.models import Engagement, EngagementStatus, UserRole
from src.clientdesk_ai.ui.theme import configure_modern_table, STATUS_BADGE_STYLES, get_service_badge_style


class ReviewQueueView(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.selected_engagement_id = None
        self._all_engagements: List[Engagement] = []
        self.init_ui()

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

        # 1. Header
        header_layout = QHBoxLayout()
        title_box = QVBoxLayout()
        title_lbl = QLabel("Senior Review & Quality Sign-Off Queue")
        title_lbl.setStyleSheet("font-size: 18px; font-weight: 700; color: #0F172A;")
        sub_lbl = QLabel("Inspect compliance checklists, enforce 4-eyes segregation of duties, and authorize client deliverables.")
        sub_lbl.setStyleSheet("font-size: 12.5px; color: #64748B;")
        title_box.addWidget(title_lbl)
        title_box.addWidget(sub_lbl)
        header_layout.addLayout(title_box)
        header_layout.addStretch()

        btn_refresh = QPushButton("🔄 Refresh Queue")
        btn_refresh.setProperty("class", "btn-secondary")
        btn_refresh.setMinimumHeight(32)
        btn_refresh.clicked.connect(self.refresh_data)
        header_layout.addWidget(btn_refresh)
        layout.addLayout(header_layout)

        # 2. Executive Review KPI Metric Cards (utilizes top open area compactly)
        cards_grid = QGridLayout()
        cards_grid.setSpacing(10)

        self.card_awaiting = self.create_kpi_card("AWAITING SENIOR REVIEW", "0", "#DC2626")
        self.card_my_reviews = self.create_kpi_card("MY DESIGNATED REVIEWS", "0", "#2563EB")
        self.card_returned = self.create_kpi_card("RETURNED FOR CORRECTION", "0", "#D97706")
        self.card_approved = self.create_kpi_card("QUALITY SIGNOFFS (APPROVED)", "0", "#059669")

        cards_grid.addWidget(self.card_awaiting, 0, 0)
        cards_grid.addWidget(self.card_my_reviews, 0, 1)
        cards_grid.addWidget(self.card_returned, 0, 2)
        cards_grid.addWidget(self.card_approved, 0, 3)
        layout.addLayout(cards_grid)

        # 3. Filter & Compliance Banner Toolbar Card
        filter_card = QFrame()
        filter_card.setProperty("class", "card")
        filter_card.setFixedHeight(46)
        fc_layout = QHBoxLayout(filter_card)
        fc_layout.setContentsMargins(12, 6, 12, 6)
        fc_layout.setSpacing(10)

        lbl_filter = QLabel("<b>Filter:</b>")
        lbl_filter.setStyleSheet("color: #0F172A; font-size: 12px;")
        fc_layout.addWidget(lbl_filter)

        self.filter_combo = QComboBox()
        self.filter_combo.setFixedHeight(28)
        self.filter_combo.addItems([
            "All Awaiting Senior Review",
            "Assigned to Me (Designated Reviewer)",
            "Returned for Correction",
            "All Active Engagements"
        ])
        self.filter_combo.currentIndexChanged.connect(self.filter_queue)
        fc_layout.addWidget(self.filter_combo)

        self.search_edit = QLineEdit()
        self.search_edit.setFixedHeight(28)
        self.search_edit.setPlaceholderText("Filter by client name, service, or operator...")
        self.search_edit.textChanged.connect(self.filter_queue)
        fc_layout.addWidget(self.search_edit)

        fc_layout.addStretch()

        sod_pill = QLabel("🛡️ 4-Eyes Principle: Assigned operators cannot review or approve their own filings")
        sod_pill.setFixedHeight(26)
        sod_pill.setStyleSheet(
            "color: #0369A1; font-size: 11px; font-weight: 600; background-color: #F0F9FF; "
            "border: 1px solid #BAE6FD; border-radius: 4px; padding: 3px 8px;"
        )
        fc_layout.addWidget(sod_pill)
        layout.addWidget(filter_card)

        # 4. Splitter: Queue List on Left, Inspection Pane on Right
        splitter = QSplitter(Qt.Orientation.Horizontal)

        left_card = QFrame()
        left_card.setProperty("class", "card")
        left_card.setMinimumWidth(460)
        left_layout = QVBoxLayout(left_card)
        left_layout.setContentsMargins(12, 12, 12, 12)
        left_layout.setSpacing(8)

        self.q_title = QLabel("Engagements Awaiting Review")
        self.q_title.setStyleSheet("font-size: 14px; font-weight: 600; color: #0F172A;")
        left_layout.addWidget(self.q_title)

        self.queue_table = QTableWidget()
        self.queue_table.setColumnCount(4)
        self.queue_table.setHorizontalHeaderLabels(["ID", "Client", "Service", "Operator"])
        self.queue_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.queue_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.queue_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.queue_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.queue_table.setColumnWidth(0, 95)
        self.queue_table.setColumnWidth(1, 115)
        self.queue_table.setColumnWidth(3, 145)
        self.queue_table.horizontalHeader().setMinimumSectionSize(85)
        self.queue_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        configure_modern_table(self.queue_table)
        self.queue_table.itemSelectionChanged.connect(self.on_queue_item_selected)
        left_layout.addWidget(self.queue_table)

        splitter.addWidget(left_card)

        # Right Inspection Pane
        right_card = QFrame()
        right_card.setProperty("class", "card")
        right_layout = QVBoxLayout(right_card)
        right_layout.setContentsMargins(16, 16, 16, 16)
        right_layout.setSpacing(12)

        self.inspect_title = QLabel("Select an engagement from the queue to perform review.")
        self.inspect_title.setStyleSheet("font-size: 15px; font-weight: 700; color: #0F172A;")
        right_layout.addWidget(self.inspect_title)

        # Segregation of Duties (4-Eyes Principle) Warning Banner & Quick Reassign
        self.sod_banner = QFrame()
        self.sod_banner.setStyleSheet(
            "background-color: #FEF3C7; border: 1.5px solid #F59E0B; border-radius: 6px; padding: 6px 10px;"
        )
        sod_b_layout = QHBoxLayout(self.sod_banner)
        sod_b_layout.setContentsMargins(8, 4, 8, 4)
        sod_b_layout.setSpacing(10)

        self.sod_banner_lbl = QLabel(
            "⚠️ <b>4-Eyes Principle:</b> You are designated as Operator for this filing. "
            "To approve, switch user profile in top bar (e.g. to Senior Reviewer Priya Sharma), or reassign operator to Staff."
        )
        self.sod_banner_lbl.setStyleSheet("color: #92400E; font-size: 11.5px;")
        self.sod_banner_lbl.setWordWrap(True)

        self.btn_reassign_staff = QPushButton("🔄 Reassign Operator to Staff")
        self.btn_reassign_staff.setProperty("class", "btn-secondary")
        self.btn_reassign_staff.setStyleSheet("padding: 4px 10px; font-size: 11px; font-weight: 700; color: #1D4ED8;")
        self.btn_reassign_staff.clicked.connect(self.reassign_current_operator_to_staff)

        sod_b_layout.addWidget(self.sod_banner_lbl, 1)
        sod_b_layout.addWidget(self.btn_reassign_staff)
        self.sod_banner.setVisible(False)
        right_layout.addWidget(self.sod_banner)

        self.inspect_table = QTableWidget()
        self.inspect_table.setColumnCount(5)
        self.inspect_table.setHorizontalHeaderLabels(["Document Name", "Requirement", "Status", "Attached File", "Remarks / Audit"])
        self.inspect_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.inspect_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.inspect_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.inspect_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.inspect_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.inspect_table.setColumnWidth(1, 130)
        self.inspect_table.setColumnWidth(2, 155)
        self.inspect_table.setColumnWidth(3, 195)
        self.inspect_table.horizontalHeader().setMinimumSectionSize(90)
        self.inspect_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        configure_modern_table(self.inspect_table)
        right_layout.addWidget(self.inspect_table)

        # Reviewer Observations Box
        obs_lbl = QLabel("Reviewer Observations & Quality Notes *:")
        obs_lbl.setStyleSheet("font-weight: 600; color: #0F172A;")
        right_layout.addWidget(obs_lbl)

        self.obs_edit = QTextEdit()
        self.obs_edit.setPlaceholderText("Enter review findings, approval comments, or reasons for return...")
        self.obs_edit.setFixedHeight(75)
        right_layout.addWidget(self.obs_edit)

        # Action Buttons
        btn_box = QHBoxLayout()

        self.btn_return = QPushButton("Return for Correction")
        self.btn_return.setProperty("class", "btn-danger")
        self.btn_return.setMinimumHeight(36)
        self.btn_return.clicked.connect(lambda: self.record_decision(False))

        self.btn_approve = QPushButton("Approve Engagement & Authorize Completion")
        self.btn_approve.setProperty("class", "btn-success")
        self.btn_approve.setMinimumHeight(36)
        self.btn_approve.clicked.connect(lambda: self.record_decision(True))

        self.role_notice_lbl = QLabel("🔒 Only Seniors/Partners can review and sign off.")
        self.role_notice_lbl.setStyleSheet("color: #64748B; font-size: 13px; font-weight: 500; font-style: italic;")
        self.role_notice_lbl.setVisible(False)

        btn_box.addWidget(self.btn_return)
        btn_box.addWidget(self.role_notice_lbl)
        btn_box.addStretch()
        btn_box.addWidget(self.btn_approve)
        right_layout.addLayout(btn_box)

        splitter.addWidget(right_card)
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([380, 720])
        layout.addWidget(splitter, 1)

    def refresh_data(self):
        # Security: Staff & Read-Only users cannot approve/return reviews
        user = getattr(self.main_window, "current_user", None)
        is_restricted = user is not None and user.role in (UserRole.STAFF, UserRole.READ_ONLY)
        self.btn_approve.setVisible(not is_restricted)
        self.btn_return.setVisible(not is_restricted)
        self.role_notice_lbl.setVisible(is_restricted)
        self.obs_edit.setEnabled(not is_restricted)

        user_id = user.user_id if user else 1
        all_engs = self.main_window.engagement_service.list_engagements()
        self._all_engagements = all_engs

        # Calculate live KPI counts
        awaiting_count = sum(1 for e in all_engs if e.status in (EngagementStatus.SUBMITTED_FOR_REVIEW, EngagementStatus.UNDER_REVIEW))
        my_review_count = sum(1 for e in all_engs if e.status in (EngagementStatus.SUBMITTED_FOR_REVIEW, EngagementStatus.UNDER_REVIEW) and e.reviewer_id == user_id)
        returned_count = sum(1 for e in all_engs if e.status == EngagementStatus.RETURNED_FOR_CORRECTION)
        approved_count = sum(1 for e in all_engs if e.status in (EngagementStatus.APPROVED, EngagementStatus.COMPLETED))

        self.card_awaiting.findChild(QLabel, "kpi_value").setText(str(awaiting_count))
        self.card_my_reviews.findChild(QLabel, "kpi_value").setText(str(my_review_count))
        self.card_returned.findChild(QLabel, "kpi_value").setText(str(returned_count))
        self.card_approved.findChild(QLabel, "kpi_value").setText(str(approved_count))

        self.filter_queue()

    def filter_queue(self):
        user = getattr(self.main_window, "current_user", None)
        user_id = user.user_id if user else 1
        filter_mode = self.filter_combo.currentIndex()
        search_term = self.search_edit.text().strip().lower()

        filtered: List[Engagement] = []
        for eng in self._all_engagements:
            # Mode filtering
            if filter_mode == 0:  # All Awaiting Senior Review
                if eng.status not in (EngagementStatus.SUBMITTED_FOR_REVIEW, EngagementStatus.UNDER_REVIEW):
                    continue
            elif filter_mode == 1:  # Assigned to Me
                if eng.status not in (EngagementStatus.SUBMITTED_FOR_REVIEW, EngagementStatus.UNDER_REVIEW) or eng.reviewer_id != user_id:
                    continue
            elif filter_mode == 2:  # Returned for Correction
                if eng.status != EngagementStatus.RETURNED_FOR_CORRECTION:
                    continue
            # filter_mode == 3 includes all active

            # Search text filtering
            if search_term:
                match_text = f"{eng.client_name} {eng.service_name} {eng.assigned_name or ''}".lower()
                if search_term not in match_text:
                    continue

            filtered.append(eng)

        self.queue_table.setRowCount(0)
        self.q_title.setText(f"Engagements in Queue ({len(filtered)})")

        for idx, eng in enumerate(filtered):
            self.queue_table.insertRow(idx)
            self.queue_table.setItem(idx, 0, QTableWidgetItem(f"ENG-{eng.engagement_id:04d}"))
            self.queue_table.setItem(idx, 1, QTableWidgetItem(eng.client_name))
            self.queue_table.setItem(idx, 2, QTableWidgetItem(eng.service_name))
            self.queue_table.setItem(idx, 3, QTableWidgetItem(eng.assigned_name or "-"))

        if filtered:
            if self.selected_engagement_id:
                # Keep previously selected engagement if still in list
                matched = False
                for r in range(self.queue_table.rowCount()):
                    eid_text = self.queue_table.item(r, 0).text()
                    if eid_text == f"ENG-{self.selected_engagement_id:04d}":
                        self.queue_table.selectRow(r)
                        matched = True
                        break
                if not matched:
                    self.queue_table.selectRow(0)
            else:
                self.queue_table.selectRow(0)
        else:
            self.inspect_title.setText("No engagements match the current review filter.")
            self.inspect_table.setRowCount(0)
            self.selected_engagement_id = None

    def on_queue_item_selected(self):
        selected_rows = self.queue_table.selectionModel().selectedRows()
        if not selected_rows:
            return

        row = selected_rows[0].row()
        eng_id_str = self.queue_table.item(row, 0).text()
        eng_id = int(eng_id_str.replace("ENG-", ""))
        self.selected_engagement_id = eng_id

        eng = self.main_window.engagement_repo.get_by_id(eng_id)
        if not eng:
            return

        self.inspect_title.setText(f"Reviewing ENG-{eng.engagement_id:04d} — {eng.client_name} ({eng.service_name}) [Status: {eng.status.value}]")

        # Segregation of Duties Check
        user = getattr(self.main_window, "current_user", None)
        user_id = user.user_id if user else 1
        is_self_assigned = (eng.assigned_to == user_id)
        if hasattr(self, "sod_banner"):
            self.sod_banner.setVisible(is_self_assigned)
        if is_self_assigned:
            self.btn_approve.setEnabled(False)
            self.btn_approve.setToolTip("Segregation of Duties: You cannot approve an engagement assigned to yourself. Switch user profile or reassign operator to Staff.")
        else:
            self.btn_approve.setEnabled(True)
            self.btn_approve.setToolTip("")

        items = self.main_window.engagement_repo.get_items(eng_id)

        attachments_map = {}
        try:
            if hasattr(self.main_window, "attachment_service"):
                attachments_map = self.main_window.attachment_service.get_attachments_for_engagement(eng_id)
        except Exception:
            pass

        self.inspect_table.setRowCount(0)
        for idx, itm in enumerate(items):
            self.inspect_table.insertRow(idx)

            item_atts = attachments_map.get(itm.engagement_item_id, [])
            has_attachment = bool(item_atts)

            # Col 0: Document Name (Prefixed with 📎 if evidence attached)
            doc_label = f"📎 {itm.document_name_snapshot}" if has_attachment else itm.document_name_snapshot
            self.inspect_table.setItem(idx, 0, QTableWidgetItem(doc_label))

            # Col 1: Requirement Badge (Clear padding, no clipping)
            req_val = itm.requirement_snapshot.value
            req_style = STATUS_BADGE_STYLES.get(req_val, "background-color: #F1F5F9; color: #475569; font-weight: 700; font-size: 11px; border-radius: 4px; padding: 2px 6px;")
            req_badge = QLabel(req_val)
            req_badge.setStyleSheet(req_style)
            req_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            req_badge.setMinimumWidth(95)
            req_box = QWidget()
            req_box.setStyleSheet("background: transparent;")
            req_layout = QHBoxLayout(req_box)
            req_layout.setContentsMargins(4, 2, 4, 2)
            req_layout.addWidget(req_badge)
            self.inspect_table.setItem(idx, 1, QTableWidgetItem(req_val))
            self.inspect_table.setCellWidget(idx, 1, req_box)

            # Col 2: Status Badge (Clear padding, no clipping)
            status_val = itm.collection_status.value
            status_display = status_val.replace('_', ' ')
            status_style = STATUS_BADGE_STYLES.get(status_val, "background-color: #F1F5F9; color: #475569; font-weight: 700; font-size: 11px; border-radius: 4px; padding: 2px 6px;")
            status_badge = QLabel(status_display)
            status_badge.setStyleSheet(status_style)
            status_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            status_badge.setMinimumWidth(115)
            status_box = QWidget()
            status_box.setStyleSheet("background: transparent;")
            status_layout = QHBoxLayout(status_box)
            status_layout.setContentsMargins(4, 2, 4, 2)
            status_layout.addWidget(status_badge)
            self.inspect_table.setItem(idx, 2, QTableWidgetItem(status_display))
            self.inspect_table.setCellWidget(idx, 2, status_box)

            # Col 3: Attached File (Clickable to verify supporting evidence)
            if has_attachment:
                first_att = item_atts[0]
                size_kb = max(1, round(first_att.file_size_bytes / 1024))
                if len(item_atts) == 1:
                    btn_att = QPushButton(f"📎 {first_att.original_filename} ({size_kb} KB)")
                    btn_att.setToolTip(f"Supporting File: {first_att.original_filename}\nSize: {size_kb} KB\nClick to inspect document")
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
                self.inspect_table.setItem(idx, 3, QTableWidgetItem(""))
                self.inspect_table.setCellWidget(idx, 3, att_box)
            else:
                lbl_none = QLabel("— No File —")
                lbl_none.setStyleSheet("color: #94A3B8; font-size: 11px; font-style: italic;")
                lbl_none.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lbl_none.setToolTip("No file uploaded by operator for this item.")
                none_box = QWidget()
                none_box.setStyleSheet("background: transparent;")
                nb_layout = QHBoxLayout(none_box)
                nb_layout.setContentsMargins(4, 2, 4, 2)
                nb_layout.addWidget(lbl_none)
                self.inspect_table.setItem(idx, 3, QTableWidgetItem(""))
                self.inspect_table.setCellWidget(idx, 3, none_box)

            # Col 4: Remarks / Audit
            remarks = itm.waiver_reason or itm.deficiency_reason or itm.internal_remarks or "-"
            self.inspect_table.setItem(idx, 4, QTableWidgetItem(remarks))

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
        """Display a list of multiple files attached to a single checklist item for senior review."""
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

            btn_open = QPushButton("Inspect")
            btn_open.setProperty("class", "btn-secondary")
            btn_open.clicked.connect(lambda _, a=att: self.open_attachment_file(a))
            table.setCellWidget(r, 2, btn_open)

        d_layout.addWidget(table)

        btn_close = QPushButton("Close")
        btn_close.setProperty("class", "btn-secondary")
        btn_close.clicked.connect(dlg.accept)
        d_layout.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignRight)
        dlg.exec()

    def reassign_current_operator_to_staff(self):
        """Reassign assigned operator to a staff user to resolve Segregation of Duties conflicts."""
        if not self.selected_engagement_id:
            return

        users = self.main_window.user_repo.list_all()
        # Find staff user (prefer nasir/staff)
        staff_users = [u for u in users if u.role == UserRole.STAFF]
        if not staff_users:
            staff_users = [u for u in users if u.user_id != self.main_window.current_user.user_id]

        if not staff_users:
            QMessageBox.warning(self, "No Staff User", "No other staff user exists in the system to reassign.")
            return

        target_staff = staff_users[0]
        self.main_window.engagement_repo.reassign_operator(self.selected_engagement_id, target_staff.user_id)
        QMessageBox.information(
            self, "Operator Reassigned",
            f"Assigned operator successfully updated to: {target_staff.full_name} ({target_staff.username}).\n\n"
            "The 4-Eyes Principle is now satisfied! You can now review and approve this filing as Admin/Partner."
        )
        self.refresh_data()
        self.load_engagement_inspection(self.selected_engagement_id)

    def record_decision(self, is_approved: bool):
        if not self.selected_engagement_id:
            QMessageBox.information(self, "Selection Required", "Please select an engagement to review.")
            return

        obs = self.obs_edit.toPlainText().strip()
        if not obs:
            QMessageBox.warning(self, "Observations Required", "Please enter mandatory review remarks / observations.")
            return

        ok, msg = self.main_window.engagement_service.perform_review(
            self.selected_engagement_id, self.main_window.current_user, is_approved, obs
        )
        if not ok:
            QMessageBox.warning(self, "Review Denied", msg)
            return

        QMessageBox.information(self, "Review Completed", msg)
        self.obs_edit.clear()
        self.selected_engagement_id = None
        self.refresh_data()
        self.main_window.dashboard_view.refresh_data()
        self.main_window.workspace_view.refresh_data()
