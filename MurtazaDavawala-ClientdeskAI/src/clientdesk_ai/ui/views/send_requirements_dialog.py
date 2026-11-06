"""Dialog to format, preview, and dispatch consolidated document checklists to clients via WhatsApp/Email.

Supports single-service and multi-service selection with distinct service color badges,
strictly excluding exempt, waived, and not-applicable requirements from collection.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict

from src.clientdesk_ai.ui.qt_compat import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit,
    QCheckBox, QScrollArea, QFrame, QMessageBox, QApplication, QComboBox,
    QWidget, Qt
)
from src.clientdesk_ai.domain.models import (
    Engagement, EngagementChecklistItem, DocumentStatus, FollowUpLog, EngagementStatus,
    ApplicabilityStatus
)
from src.clientdesk_ai.security.crypto import mask_pan, mask_gstin, mask_aadhaar
from src.clientdesk_ai.ui.theme import get_service_badge_style


class SendRequirementsDialog(QDialog):
    """Consolidated document collection dispatch dialog with multi-service support."""

    def __init__(self, main_window, engagement_id: Optional[int] = None, client_id: Optional[int] = None,
                 is_follow_up: bool = False, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.initial_engagement_id = engagement_id
        self.selected_client_id = client_id
        self.is_follow_up = is_follow_up

        # If engagement_id is provided, resolve client_id from engagement
        if engagement_id:
            eng = self.main_window.engagement_repo.get_by_id(engagement_id)
            if eng:
                self.selected_client_id = eng.client_id

        self.service_checkboxes: Dict[int, QCheckBox] = {}
        self.item_checkboxes: List[QCheckBox] = []
        self.current_format = "EMAIL" if is_follow_up else "WHATSAPP"

        self.setWindowTitle("Dispatch Requirement Checklist to Client")
        self.resize(820, 720)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # 1. Client Header & Switcher Card
        header_card = QFrame()
        header_card.setStyleSheet("background-color: #1E3A8A; border-radius: 8px; padding: 12px;")
        h_layout = QVBoxLayout(header_card)
        h_layout.setSpacing(6)

        client_row = QHBoxLayout()
        c_title_lbl = QLabel("<span style='color: #DBEAFE; font-size: 11px; font-weight: 600; text-transform: uppercase;'>Target Client Entity</span>")
        client_row.addWidget(c_title_lbl)
        client_row.addStretch()

        self.client_combo = QComboBox()
        self.client_combo.setStyleSheet(
            "background-color: #1E40AF; color: #FFFFFF; border: 1px solid #3B82F6; padding: 4px 10px; border-radius: 4px; font-weight: 600;"
        )
        clients = self.main_window.client_service.search_clients("")
        selected_idx = 0
        for idx, c in enumerate(clients):
            self.client_combo.addItem(f"{c.client_name} ({c.client_code})", c.client_id)
            if self.selected_client_id and c.client_id == self.selected_client_id:
                selected_idx = idx

        if clients:
            self.client_combo.setCurrentIndex(selected_idx)
            self.selected_client_id = self.client_combo.currentData()

        self.client_combo.currentIndexChanged.connect(self.on_client_changed)
        client_row.addWidget(self.client_combo)
        h_layout.addLayout(client_row)

        info_box = QVBoxLayout()
        info_box.setSpacing(4)
        self.client_info_lbl = QLabel()
        self.client_info_lbl.setStyleSheet("color: #E2E8F0; font-size: 13px;")

        self.chk_mask_identifiers = QCheckBox("🔒 Mask PAN / Aadhaar in External Client Dispatch (Statutory Privacy)")
        self.chk_mask_identifiers.setChecked(True)  # Privacy compliance by default when sending data requirements
        self.chk_mask_identifiers.setToolTip(
            "Masks PAN (AB*******F) and Aadhaar (********1234) when sending requirements to client via WhatsApp, Email, or PDF export to comply with statutory privacy rules."
        )
        self.chk_mask_identifiers.setStyleSheet("font-size: 11px; font-weight: 600; color: #38BDF8;")
        self.chk_mask_identifiers.stateChanged.connect(self.on_privacy_mask_toggled)

        info_box.addWidget(self.client_info_lbl)
        info_box.addWidget(self.chk_mask_identifiers)
        h_layout.addLayout(info_box)
        layout.addWidget(header_card)

        # 2. Multi-Service Selection Section
        svc_header_layout = QHBoxLayout()
        svc_title = QLabel("<b>Select Statutory Services to Include in Request:</b>")
        svc_title.setStyleSheet("color: #0F172A; font-size: 13px;")
        svc_header_layout.addWidget(svc_title)
        svc_header_layout.addStretch()

        btn_select_all_svc = QPushButton("Select All")
        btn_select_all_svc.setProperty("class", "btn-secondary")
        btn_select_all_svc.setStyleSheet("font-size: 11px; padding: 3px 8px;")
        btn_select_all_svc.clicked.connect(lambda: self.toggle_all_services(True))

        btn_clear_svc = QPushButton("Deselect All")
        btn_clear_svc.setProperty("class", "btn-secondary")
        btn_clear_svc.setStyleSheet("font-size: 11px; padding: 3px 8px;")
        btn_clear_svc.clicked.connect(lambda: self.toggle_all_services(False))

        svc_header_layout.addWidget(btn_select_all_svc)
        svc_header_layout.addWidget(btn_clear_svc)
        layout.addLayout(svc_header_layout)

        self.services_container = QFrame()
        self.services_container.setStyleSheet("background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; padding: 8px;")
        self.services_layout = QVBoxLayout(self.services_container)
        self.services_layout.setSpacing(6)
        layout.addWidget(self.services_container)

        # 3. Pending Checklist Items Area — with Pending-Only filter toggle
        items_header_layout = QHBoxLayout()
        items_title = QLabel("<b>Documents for Selected Services:</b> <span style='font-size: 11px; color: #64748B;'>(Exempt and waived items excluded)</span>")
        items_title.setStyleSheet("color: #0F172A; font-size: 13px;")
        items_header_layout.addWidget(items_title)
        items_header_layout.addStretch()

        # Pending-Only filter toggle
        self.chk_pending_only = QCheckBox("Pending Only (Hide Accepted / Waived)")
        self.chk_pending_only.setToolTip(
            "When checked, already-accepted and waived items are hidden — useful for follow-up reminders."
        )
        self.chk_pending_only.setStyleSheet("font-size: 12px; font-weight: 600; color: #D97706;")
        self.chk_pending_only.setChecked(self.is_follow_up)  # auto-enable for follow-ups
        self.chk_pending_only.stateChanged.connect(self.on_service_selection_changed)
        items_header_layout.addWidget(self.chk_pending_only)

        layout.addLayout(items_header_layout)

        self.items_scroll = QScrollArea()
        self.items_scroll.setWidgetResizable(True)
        self.items_scroll.setFixedHeight(140)
        self.items_content = QFrame()
        self.items_layout = QVBoxLayout(self.items_content)
        self.items_layout.setContentsMargins(8, 8, 8, 8)
        self.items_layout.setSpacing(6)
        self.items_scroll.setWidget(self.items_content)
        layout.addWidget(self.items_scroll)

        # 4. Format Switcher Buttons (WhatsApp vs Email)
        btn_switch_layout = QHBoxLayout()
        self.btn_fmt_wa = QPushButton("📱 WhatsApp Format")
        self.btn_fmt_wa.setProperty("class", "btn-secondary" if self.is_follow_up else "btn-primary")
        self.btn_fmt_wa.clicked.connect(lambda: self.set_format("WHATSAPP"))

        self.btn_fmt_email = QPushButton("📧 Email Draft Format")
        self.btn_fmt_email.setProperty("class", "btn-primary" if self.is_follow_up else "btn-secondary")
        self.btn_fmt_email.clicked.connect(lambda: self.set_format("EMAIL"))

        btn_switch_layout.addWidget(self.btn_fmt_wa)
        btn_switch_layout.addWidget(self.btn_fmt_email)
        btn_switch_layout.addStretch()
        layout.addLayout(btn_switch_layout)

        # 5. Message Preview Editor
        self.msg_edit = QTextEdit()
        self.msg_edit.setStyleSheet(
            "font-family: Consolas, 'Segoe UI', monospace; font-size: 13px; line-height: 1.5; background-color: #FFFFFF; border: 1.5px solid #CBD5E1; border-radius: 6px; padding: 10px;"
        )
        layout.addWidget(self.msg_edit)

        # 6. Bottom Action Bar
        bottom_layout = QHBoxLayout()

        btn_copy = QPushButton("📋 Copy to Clipboard")
        btn_copy.setProperty("class", "btn-secondary")
        btn_copy.setMinimumHeight(36)
        btn_copy.clicked.connect(self.copy_to_clipboard)

        self.btn_send_email = QPushButton("📧 Send via Email Now")
        self.btn_send_email.setProperty("class", "btn-primary")
        self.btn_send_email.setMinimumHeight(36)
        self.btn_send_email.clicked.connect(self.send_via_email_now)

        self.btn_mark_sent = QPushButton("📤 Mark as Requested & Record Follow-Up")
        self.btn_mark_sent.setProperty("class", "btn-success")
        self.btn_mark_sent.setMinimumHeight(36)
        self.btn_mark_sent.clicked.connect(self.record_sent_and_update_status)

        btn_close = QPushButton("Close")
        btn_close.setProperty("class", "btn-secondary")
        btn_close.setMinimumHeight(36)
        btn_close.clicked.connect(self.accept)

        bottom_layout.addWidget(btn_copy)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.btn_send_email)
        bottom_layout.addWidget(self.btn_mark_sent)
        bottom_layout.addWidget(btn_close)
        layout.addLayout(bottom_layout)

        # Initial data population
        self.on_client_changed()

    def on_privacy_mask_toggled(self):
        """Update client metadata display and regenerate checklist dispatch message when privacy mask is toggled."""
        self.update_client_info_display()
        self.regenerate_message()

    def update_client_info_display(self):
        if not self.selected_client_id:
            return
        client = self.main_window.client_repo.get_by_id(self.selected_client_id)
        if not client:
            return

        is_masked = hasattr(self, "chk_mask_identifiers") and self.chk_mask_identifiers.isChecked()
        pan_text = (mask_pan(client.pan) if is_masked else client.pan) if client.pan else "No PAN"
        aadhaar_val = getattr(client, "aadhaar", "")
        aadhaar_text = (mask_aadhaar(aadhaar_val) if is_masked else aadhaar_val) if aadhaar_val else ""
        gstin_text = (mask_gstin(client.gstin) if is_masked else client.gstin) if client.gstin else "No GSTIN"

        parts = [f"<b>{client.client_name}</b>", f"Entity: {client.entity_type}", f"PAN: <b>{pan_text}</b>"]
        if aadhaar_text:
            parts.append(f"Aadhaar: <b>{aadhaar_text}</b>")
        if client.gstin:
            parts.append(f"GSTIN: <b>{gstin_text}</b>")

        self.client_info_lbl.setText(" | ".join(parts))

    def on_client_changed(self):
        client_id = self.client_combo.currentData()
        if not client_id:
            return
        self.selected_client_id = client_id

        # Update client info label
        self.update_client_info_display()

        # Refresh Services checkboxes for this client
        self.populate_services()

    def populate_services(self):
        # Clear existing service widgets
        while self.services_layout.count():
            item = self.services_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.service_checkboxes.clear()

        all_engagements = self.main_window.engagement_service.list_engagements(client_id=self.selected_client_id)
        # Filter active engagements (exclude COMPLETED and CANCELLED)
        active_engs = [e for e in all_engagements if e.status not in (EngagementStatus.COMPLETED, EngagementStatus.CANCELLED)]

        if not active_engs:
            empty_lbl = QLabel("<i>No active engagements found for this client. Please create an engagement first.</i>")
            empty_lbl.setStyleSheet("color: #64748B; font-size: 12px;")
            self.services_layout.addWidget(empty_lbl)
            self.populate_checklist_items([])
            return

        for eng in active_engs:
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(4, 2, 4, 2)
            row_layout.setSpacing(8)

            chk = QCheckBox()
            # If initial_engagement_id was given, check that one; otherwise check all active
            if self.initial_engagement_id:
                chk.setChecked(eng.engagement_id == self.initial_engagement_id)
            else:
                chk.setChecked(True)

            chk.setProperty("engagement_data", eng)
            chk.stateChanged.connect(self.on_service_selection_changed)

            # Color Badge Chip
            badge = QLabel(f" {eng.service_name.split('-')[0].strip()} ")
            badge.setStyleSheet(get_service_badge_style(eng.service_name))

            desc_lbl = QLabel(
                f"<b>{eng.service_name}</b> ({eng.financial_year}) — Statutory Due Date: <b>{eng.due_date}</b>"
            )
            desc_lbl.setStyleSheet("font-size: 12px; color: #1E293B;")

            row_layout.addWidget(chk)
            row_layout.addWidget(badge)
            row_layout.addWidget(desc_lbl)
            row_layout.addStretch()

            self.services_layout.addWidget(row_widget)
            self.service_checkboxes[eng.engagement_id] = chk

        self.on_service_selection_changed()

    def toggle_all_services(self, state: bool):
        for chk in self.service_checkboxes.values():
            chk.setChecked(state)

    def on_service_selection_changed(self):
        selected_eng_ids = [
            eid for eid, chk in self.service_checkboxes.items() if chk.isChecked()
        ]
        self.populate_checklist_items(selected_eng_ids)

    def populate_checklist_items(self, selected_eng_ids: List[int]):
        # Clear existing items widgets
        while self.items_layout.count():
            item = self.items_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.item_checkboxes.clear()

        if not selected_eng_ids:
            empty_lbl = QLabel("<i>Please select at least one service above to view required documents.</i>")
            empty_lbl.setStyleSheet("color: #64748B; font-size: 12px;")
            self.items_layout.addWidget(empty_lbl)
            self.regenerate_message()
            return

        pending_only = self.chk_pending_only.isChecked()
        total_shown = 0
        for eng_id in selected_eng_ids:
            eng = self.main_window.engagement_repo.get_by_id(eng_id)
            items = self.main_window.engagement_repo.get_items(eng_id)

            if pending_only:
                # Pending-only: hide ACCEPTED and WAIVED_WITH_APPROVAL; show RECEIVED and NOT_REQUESTED
                shown_items = [
                    i for i in items
                    if not i.is_exempt
                    and i.applicability_status != ApplicabilityStatus.NOT_APPLICABLE
                    and i.collection_status not in (
                        DocumentStatus.ACCEPTED,
                        DocumentStatus.WAIVED_WITH_APPROVAL,
                        DocumentStatus.NOT_APPLICABLE,
                    )
                ]
            else:
                # Full checklist: exclude only not-applicable / exempt
                shown_items = [
                    i for i in items
                    if not i.is_exempt
                    and i.applicability_status != ApplicabilityStatus.NOT_APPLICABLE
                    and i.collection_status not in (
                        DocumentStatus.ACCEPTED,
                        DocumentStatus.WAIVED_WITH_APPROVAL,
                        DocumentStatus.RECEIVED,
                        DocumentStatus.NOT_APPLICABLE,
                    )
                ]

            if not shown_items:
                continue

            total_shown += len(shown_items)

            # Service Header Group
            svc_hdr = QLabel(f"📁 <b>{eng.service_name}</b> ({eng.financial_year})")
            svc_hdr.setStyleSheet(
                "font-size: 12px; font-weight: 700; color: #0F172A; margin-top: 4px; padding: 2px 4px; background-color: #F1F5F9; border-radius: 4px;"
            )
            self.items_layout.addWidget(svc_hdr)

            for itm in shown_items:
                status_tag = ""
                if itm.collection_status == DocumentStatus.RECEIVED:
                    status_tag = " ✉️[Received — Awaiting Verification]"
                elif itm.collection_status == DocumentStatus.DEFICIENT:
                    status_tag = " ⚠️[Deficient]"
                chk = QCheckBox(f"{itm.document_name_snapshot} ({itm.category_name} - {itm.requirement_snapshot.value}){status_tag}")
                chk.setChecked(True)
                chk.setProperty("item_data", itm)
                chk.setProperty("engagement_id", eng_id)
                chk.stateChanged.connect(self.regenerate_message)
                self.items_layout.addWidget(chk)
                self.item_checkboxes.append(chk)

        if total_shown == 0:
            if pending_only:
                ok_lbl = QLabel("<i>✅ All items accepted or waived — no pending documents for the selected services!</i>")
            else:
                ok_lbl = QLabel("<i>All required documents for selected services have already been accepted or exempted!</i>")
            ok_lbl.setStyleSheet("color: #059669; font-weight: 600; font-size: 12px;")
            self.items_layout.addWidget(ok_lbl)

        self.items_layout.addStretch()
        self.regenerate_message()

    def set_format(self, fmt: str):
        self.current_format = fmt
        if fmt == "WHATSAPP":
            self.btn_fmt_wa.setProperty("class", "btn-primary")
            self.btn_fmt_email.setProperty("class", "btn-secondary")
        else:
            self.btn_fmt_wa.setProperty("class", "btn-secondary")
            self.btn_fmt_email.setProperty("class", "btn-primary")

        self.btn_fmt_wa.style().unpolish(self.btn_fmt_wa)
        self.btn_fmt_wa.style().polish(self.btn_fmt_wa)
        self.btn_fmt_email.style().unpolish(self.btn_fmt_email)
        self.btn_fmt_email.style().polish(self.btn_fmt_email)

        self.regenerate_message()

    def get_selected_items_by_engagement(self) -> Dict[int, List[EngagementChecklistItem]]:
        res: Dict[int, List[EngagementChecklistItem]] = {}
        for chk in self.item_checkboxes:
            if chk.isChecked():
                eng_id = chk.property("engagement_id")
                itm = chk.property("item_data")
                if eng_id not in res:
                    res[eng_id] = []
                res[eng_id].append(itm)
        return res

    def regenerate_message(self):
        items_by_eng = self.get_selected_items_by_engagement()
        client = self.main_window.client_repo.get_by_id(self.selected_client_id)
        client_name = client.client_name if client else "Valued Client"
        pending_only = hasattr(self, "chk_pending_only") and self.chk_pending_only.isChecked()

        if not items_by_eng:
            self.msg_edit.setPlainText("No pending documents selected. Check at least one service and document above.")
            return

        is_masked = hasattr(self, "chk_mask_identifiers") and self.chk_mask_identifiers.isChecked()
        pan_val = (mask_pan(client.pan) if is_masked else client.pan) if client and client.pan else ""

        if self.current_format == "WHATSAPP":
            lines = [
                "*DOCUMENT REQUIREMENT CHECKLIST*",
                f"Client: *{client_name}*",
            ]
            if pan_val:
                lines.append(f"PAN: *{pan_val}*")
            lines.extend([
                f"Date: *{datetime.now().strftime('%d-%b-%Y')}*",
                "",
            ])
            if pending_only:
                lines.append("Dear Client, thank you for your previous submissions. To proceed with your compliance work, we still require the following pending documents:")
            else:
                lines.append("Dear Client,")
                lines.append("To initiate and proceed with your statutory compliance filings, kindly share clear copies of the following documents:")
            lines.append("")

            svc_counter = 1
            for eng_id, items in items_by_eng.items():
                eng = self.main_window.engagement_repo.get_by_id(eng_id)
                lines.append(f"📁 *SERVICE {svc_counter}: {eng.service_name} ({eng.financial_year})*")
                lines.append(f"Statutory Due Date: *{eng.due_date}*")
                for idx, itm in enumerate(items, 1):
                    lines.append(f"  {idx}. *{itm.document_name_snapshot}* ({itm.category_name})")
                lines.append("")
                svc_counter += 1

            lines.extend([
                "⚠️ *Submission Guidelines:*",
                "• All documents must be clear, legible color scans or official PDF downloads.",
                "• Utility bills must not be older than 2 months.",
                "• If any item does not apply to your entity, kindly notify our desk.",
                "",
                "Kindly reply with the attachments at your earliest convenience to ensure timely filing.",
                "Thank you,",
                "Clientdesk AI Compliance Team"
            ])
            self.msg_edit.setPlainText("\n".join(lines))
        else:
            services_summary = ", ".join(
                self.main_window.engagement_repo.get_by_id(eid).service_name
                for eid in items_by_eng.keys()
            )
            if pending_only:
                subject_prefix = "Follow-Up: Pending Documents Required —"
                intro = (
                    f"Dear Client,\n\n"
                    f"This is a gentle reminder regarding the pending documents required for your compliance work for {client_name}. "
                    f"Thank you for the documents already submitted. We still require the following to proceed:\n"
                )
            else:
                subject_prefix = "Consolidated Document Checklist:"
                intro = (
                    f"Dear Client,\n\n"
                    f"We are initiating statutory compliance work for {client_name}. "
                    f"To ensure accurate filing and complete adherence to regulatory deadlines, please provide the required supporting documents listed below:\n"
                )

            lines = [
                f"Subject: {subject_prefix} {services_summary} — {client_name}",
                "",
                intro,
            ]

            svc_counter = 1
            for eng_id, items in items_by_eng.items():
                eng = self.main_window.engagement_repo.get_by_id(eng_id)
                lines.append(f"--- SERVICE {svc_counter}: {eng.service_name} (Period: {eng.financial_year}) ---")
                lines.append(f"Statutory Due Date: {eng.due_date}")
                for idx, itm in enumerate(items, 1):
                    lines.append(f"  {idx}. {itm.document_name_snapshot} [{itm.category_name}]")
                lines.append("")
                svc_counter += 1

            lines.extend([
                "Submission Instructions:",
                "- Please provide official PDF downloads or scanned original copies.",
                "- If any condition or document does not apply to your business, please inform us so we can formally exempt it.",
                "",
                "Should you require any clarification, please feel free to reach out to our desk.",
                "",
                "Warm regards,",
                "Clientdesk AI Compliance Workspace"
            ])
            self.msg_edit.setPlainText("\n".join(lines))

    def copy_to_clipboard(self):
        text = self.msg_edit.toPlainText()
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
        QMessageBox.information(
            self, "Copied", "Consolidated checklist text copied to clipboard! You can now paste it into WhatsApp or your email client."
        )

    def generate_checklist_pdf(self, client, items_by_eng: Dict[int, List[EngagementChecklistItem]]) -> str:
        """Generate a professional styled PDF checklist using ReportLab."""
        import tempfile
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors

        # Retrieve Org Profile for header
        firm_name = "Clientdesk AI Practice Management"
        tagline = "Professional Chartered Accountants & Compliance Advisors"
        try:
            from src.clientdesk_ai.persistence.database import get_db_connection
            conn = get_db_connection()
            row = conn.execute("SELECT firm_name, tagline FROM organisation_profile LIMIT 1;").fetchone()
            if row:
                if row["firm_name"]:
                    firm_name = row["firm_name"]
                if row["tagline"]:
                    tagline = row["tagline"]
            conn.close()
        except Exception:
            pass

        tmp_pdf = tempfile.NamedTemporaryFile(suffix=".pdf", prefix=f"Checklist_{client.client_code}_", delete=False)
        tmp_path = tmp_pdf.name
        tmp_pdf.close()

        doc = SimpleDocTemplate(
            tmp_path,
            pagesize=letter,
            leftMargin=36,
            rightMargin=36,
            topMargin=36,
            bottomMargin=36
        )

        styles = getSampleStyleSheet()
        header_title_style = ParagraphStyle(
            "FirmHeader",
            parent=styles["Heading1"],
            fontSize=16,
            leading=20,
            textColor=colors.HexColor("#0F172A"),
            spaceAfter=2
        )
        tagline_style = ParagraphStyle(
            "FirmTagline",
            parent=styles["Normal"],
            fontSize=10,
            leading=13,
            textColor=colors.HexColor("#64748B"),
            spaceAfter=10
        )
        doc_title_style = ParagraphStyle(
            "DocTitle",
            parent=styles["Heading2"],
            fontSize=12,
            leading=15,
            textColor=colors.HexColor("#1E40AF"),
            spaceAfter=8
        )
        body_style = ParagraphStyle(
            "DocBody",
            parent=styles["Normal"],
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#1E293B")
        )
        header_cell_style = ParagraphStyle(
            "HeaderCell",
            parent=styles["Normal"],
            fontSize=9,
            leading=11,
            fontName="Helvetica-Bold",
            textColor=colors.white
        )

        story = []

        # 1. Header
        story.append(Paragraph(f"<b>{firm_name}</b>", header_title_style))
        story.append(Paragraph(tagline, tagline_style))
        story.append(Paragraph("<b>STATUTORY DOCUMENT REQUIREMENT CHECKLIST</b>", doc_title_style))

        # 2. Client Metadata Box
        is_masked = hasattr(self, "chk_mask_identifiers") and self.chk_mask_identifiers.isChecked()
        pan_str = (mask_pan(client.pan) if is_masked else client.pan) if client.pan else "N/A"
        aadhaar_val = getattr(client, "aadhaar", "")
        aadhaar_str = (mask_aadhaar(aadhaar_val) if is_masked else aadhaar_val) if aadhaar_val else "N/A"
        gstin_str = (mask_gstin(client.gstin) if is_masked else client.gstin) if client.gstin else "N/A"
        date_str = datetime.now().strftime("%d-%b-%Y")
        meta_data = [
            [
                Paragraph(f"<b>Client Name:</b> {client.client_name}", body_style),
                Paragraph(f"<b>Date:</b> {date_str}", body_style)
            ],
            [
                Paragraph(f"<b>Client Code:</b> {client.client_code}", body_style),
                Paragraph(f"<b>Entity Type:</b> {client.entity_type}", body_style)
            ],
            [
                Paragraph(f"<b>PAN:</b> {pan_str}", body_style),
                Paragraph(f"<b>Aadhaar:</b> {aadhaar_str}", body_style)
            ],
            [
                Paragraph(f"<b>GSTIN:</b> {gstin_str}", body_style),
                Paragraph(f"<b>Status:</b> {client.status}", body_style)
            ]
        ]
        meta_table = Table(meta_data, colWidths=[300, 240])
        meta_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#CBD5E1")),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(meta_table)
        story.append(Spacer(1, 12))

        # 3. Checklists by Engagement
        for eng_id, items in items_by_eng.items():
            eng = self.main_window.engagement_repo.get_by_id(eng_id)
            eng_title = f"Service: {eng.service_name} ({eng.financial_year}) — Statutory Due Date: {eng.due_date}"
            story.append(Paragraph(f"<b>{eng_title}</b>", ParagraphStyle(
                "SvcTitle", parent=styles["Heading3"], fontSize=10.5, leading=13, textColor=colors.HexColor("#0F172A"), spaceAfter=4
            )))

            table_rows = [
                [
                    Paragraph("<b>#</b>", header_cell_style),
                    Paragraph("<b>Required Document Item</b>", header_cell_style),
                    Paragraph("<b>Category</b>", header_cell_style),
                    Paragraph("<b>Format & Submission Instructions</b>", header_cell_style)
                ]
            ]
            for idx, itm in enumerate(items, 1):
                instr = itm.format_instructions or f"Allowed formats: {itm.file_formats or 'PDF, JPG'}"
                table_rows.append([
                    Paragraph(str(idx), body_style),
                    Paragraph(f"<b>{itm.document_name_snapshot}</b>", body_style),
                    Paragraph(itm.category_name, body_style),
                    Paragraph(instr, body_style)
                ])

            t = Table(table_rows, colWidths=[25, 230, 95, 190])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
                ('ALIGN', (0, 0), (0, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ('TOPPADDING', (0, 0), (-1, -1), 5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
            ]))
            story.append(t)
            story.append(Spacer(1, 10))

        # 4. Footer notes
        footer_text = (
            "<b>Submission Instructions:</b><br/>"
            "1. Please provide official digital downloads or clear color scans.<br/>"
            "2. Ensure all relevant pages and schedules are included.<br/>"
            "3. If any item is not applicable to your business, please notify our desk so it can be formally exempted."
        )
        story.append(Paragraph(footer_text, ParagraphStyle(
            "FooterNotes", parent=styles["Normal"], fontSize=8.5, leading=11, textColor=colors.HexColor("#475569")
        )))

        doc.build(story)
        return tmp_path

    def send_via_email_now(self):
        """Directly dispatch requirement checklist and generated PDF to client via SMTP."""
        client_id = self.client_combo.currentData()
        if not client_id:
            QMessageBox.warning(self, "No Client", "Please select a client first.")
            return

        client = self.main_window.client_repo.get_by_id(client_id)
        if not client or not client.email or "@" not in client.email:
            QMessageBox.warning(
                self, "Missing Email",
                f"Client '{client.client_name if client else ''}' does not have a valid email address saved in Master Records.\n\n"
                "Please update the client's email address before sending via email."
            )
            return

        items_by_eng = self.get_selected_items_by_engagement()
        if not items_by_eng:
            QMessageBox.warning(self, "No Items", "No document requirements are selected to send.")
            return

        # Ensure email format is generated in preview editor
        self.set_format("EMAIL")
        body_text = self.msg_edit.toPlainText().strip()
        if not body_text:
            self.regenerate_message()
            body_text = self.msg_edit.toPlainText().strip()

        # Subject extraction or default
        subject = f"Document Requirement Checklist — {client.client_name}"
        for line in body_text.splitlines():
            if line.lower().startswith("subject:"):
                subject = line[8:].strip()
                break

        # Generate Temporary PDF attachment
        pdf_path = None
        try:
            pdf_path = self.generate_checklist_pdf(client, items_by_eng)
        except Exception:
            pdf_path = None

        if not hasattr(self.main_window, "email_service") or not self.main_window.email_service:
            QMessageBox.critical(self, "Service Error", "Email service is not initialized.")
            return

        # Confirm dispatch
        attachment_notice = "with PDF Checklist attached" if pdf_path else "(Email text only)"
        confirm = QMessageBox.question(
            self,
            "Confirm Email Dispatch",
            f"Send document checklist email to:\n<b>{client.client_name}</b> &lt;{client.email}&gt; {attachment_notice}?\n\n"
            f"Statutory requirements will automatically be marked as REQUESTED upon sending.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        # Dispatch via EmailService
        ok, msg = self.main_window.email_service.send_checklist_email(
            to_email=client.email,
            subject=subject,
            body_text=body_text,
            pdf_path=pdf_path
        )

        if not ok:
            QMessageBox.critical(
                self, "Email Dispatch Failed",
                f"Could not send email to {client.email}:\n\n{msg}\n\n"
                "Tip: Check your SMTP host, port, and App Password in Settings & Diagnostics."
            )
            return

        # Successfully sent: update DB and record follow-up
        self.record_sent_and_update_status(mode_label="Email (SMTP)")

    def record_sent_and_update_status(self, mode_label: Optional[str] = None):
        items_by_eng = self.get_selected_items_by_engagement()
        if not items_by_eng:
            QMessageBox.information(self, "No Items", "No checklist items were selected.")
            return

        actor = self.main_window.current_user
        actor_id = actor.user_id if actor else 1
        now_dt = datetime.now(timezone.utc)
        next_followup = (now_dt + timedelta(days=3)).strftime("%Y-%m-%d")

        total_items_updated = 0
        total_engagements = len(items_by_eng)
        effective_mode = mode_label or f"Checklist Sent ({self.current_format})"

        for eng_id, items in items_by_eng.items():
            eng = self.main_window.engagement_repo.get_by_id(eng_id)

            # 1. Update collection status to REQUESTED for all selected items
            for item in items:
                if item.collection_status == DocumentStatus.NOT_REQUESTED:
                    self.main_window.checklist_service.update_item_status(
                        item.engagement_item_id, DocumentStatus.REQUESTED, actor, remarks="Requirement list dispatched to client"
                    )
                    total_items_updated += 1

            # 2. Record in FollowUpLog
            summary_text = f"Dispatched requirement checklist with {len(items)} items for {eng.service_name} via {effective_mode}."
            self.main_window.log_repo.add_follow_up(
                FollowUpLog(
                    engagement_id=eng_id,
                    user_id=actor_id,
                    communication_mode=effective_mode,
                    summary_of_request=summary_text,
                    client_response="Awaiting client document uploads",
                    next_follow_up_date=next_followup
                )
            )

            # 3. Update engagement status to IN_PROGRESS if NOT_STARTED
            if eng.status in (DocumentStatus.NOT_REQUESTED, EngagementStatus.NOT_STARTED):
                self.main_window.engagement_repo.update_status(
                    eng_id, EngagementStatus.IN_PROGRESS, actor_id, f"Checklist dispatched to client via {effective_mode}"
                )

        QMessageBox.information(
            self, "Follow-Up Recorded",
            f"Successfully dispatched checklist for {total_engagements} service(s) ({total_items_updated} items marked REQUESTED)!\nNext reminder scheduled for {next_followup}."
        )
        self.accept()
        self.main_window.dashboard_view.refresh_data()
        self.main_window.workspace_view.refresh_data()
