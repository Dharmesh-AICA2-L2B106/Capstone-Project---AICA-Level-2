"""Modern KPI Dashboard with active summaries, quick workflow shortcuts, and client requirement dispatch."""

from src.clientdesk_ai.ui.qt_compat import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QFrame, QTableWidget, QTableWidgetItem, QHeaderView, Qt
)
from src.clientdesk_ai.ui.theme import STATUS_BADGE_STYLES, configure_modern_table, get_service_badge_style
from src.clientdesk_ai.domain.models import EngagementStatus, User
from src.clientdesk_ai.ui.views.send_requirements_dialog import SendRequirementsDialog


class DashboardView(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(18)

        # Welcome Header
        header_layout = QHBoxLayout()
        title_box = QVBoxLayout()
        self.title_lbl = QLabel("Operational Workspace Overview")
        self.title_lbl.setStyleSheet("font-size: 20px; font-weight: 700; color: #0F172A;")
        self.subtitle_lbl = QLabel("Dispatch requirements to clients, track live document collection, and update records for senior review.")
        self.subtitle_lbl.setStyleSheet("font-size: 13px; color: #64748B;")
        title_box.addWidget(self.title_lbl)
        title_box.addWidget(self.subtitle_lbl)
        header_layout.addLayout(title_box)
        header_layout.addStretch()

        btn_new_client = QPushButton("+ Register Client")
        btn_new_client.setProperty("class", "btn-secondary")
        btn_new_client.clicked.connect(lambda: self.main_window.switch_tab(1))

        btn_new_eng = QPushButton("+ New Engagement")
        btn_new_eng.setProperty("class", "btn-primary")
        btn_new_eng.clicked.connect(lambda: self.main_window.switch_tab(2))

        header_layout.addWidget(btn_new_client)
        header_layout.addWidget(btn_new_eng)
        layout.addLayout(header_layout)

        # KPI Metric Cards
        cards_grid = QGridLayout()
        cards_grid.setSpacing(16)

        self.card_clients = self.create_kpi_card("ACTIVE CLIENTS", "0", "#2563EB")
        self.card_engagements = self.create_kpi_card("ACTIVE ENGAGEMENTS", "0", "#0D9488")
        self.card_pending_docs = self.create_kpi_card("DOCUMENTS PENDING", "0", "#D97706")
        self.card_review_queue = self.create_kpi_card("AWAITING SENIOR REVIEW", "0", "#DC2626")

        cards_grid.addWidget(self.card_clients, 0, 0)
        cards_grid.addWidget(self.card_engagements, 0, 1)
        cards_grid.addWidget(self.card_pending_docs, 0, 2)
        cards_grid.addWidget(self.card_review_queue, 0, 3)
        layout.addLayout(cards_grid)

        # Recent Engagements Section
        recent_box = QFrame()
        recent_box.setProperty("class", "card")
        recent_layout = QVBoxLayout(recent_box)

        rec_header = QHBoxLayout()
        rec_title = QLabel("Recent Client Engagements & Requirement Dispatch")
        rec_title.setStyleSheet("font-size: 15px; font-weight: 600; color: #0F172A;")
        rec_header.addWidget(rec_title)
        rec_header.addStretch()

        btn_multi_send = QPushButton("📤 Multi-Service Client Dispatch")
        btn_multi_send.setProperty("class", "btn-secondary")
        btn_multi_send.setStyleSheet("font-weight: 600; color: #2563EB;")
        btn_multi_send.clicked.connect(self.open_multi_service_dispatch)
        rec_header.addWidget(btn_multi_send)

        btn_view_all = QPushButton("Open Full Workspaces →")
        btn_view_all.setProperty("class", "btn-secondary")
        btn_view_all.clicked.connect(lambda: self.main_window.switch_tab(2))
        rec_header.addWidget(btn_view_all)
        recent_layout.addLayout(rec_header)

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "ID", "Client", "Service Group", "Due Date", "Status", "Operator", "Actions"
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(0, 85)
        self.table.setColumnWidth(2, 145)
        self.table.setColumnWidth(3, 105)
        self.table.setColumnWidth(4, 155)
        self.table.setColumnWidth(5, 110)
        self.table.setColumnWidth(6, 230)
        configure_modern_table(self.table)
        self.table.verticalHeader().setDefaultSectionSize(48)
        self.table.cellDoubleClicked.connect(self.on_row_double_clicked)
        recent_layout.addWidget(self.table)

        layout.addWidget(recent_box)

        # ── Follow-Up Alert Card ──────────────────────────────────────────────
        self.followup_card = QFrame()
        self.followup_card.setProperty("class", "card")
        fu_layout = QVBoxLayout(self.followup_card)

        fu_hdr = QHBoxLayout()
        fu_title = QLabel("⚠️ Action Needed: Pending Follow-Ups")
        fu_title.setStyleSheet("font-size: 15px; font-weight: 600; color: #D97706;")
        fu_hdr.addWidget(fu_title)
        fu_hdr.addStretch()
        fu_layout.addLayout(fu_hdr)

        self.followup_table = QTableWidget()
        self.followup_table.setColumnCount(6)
        self.followup_table.setHorizontalHeaderLabels(
            ["ID", "Client", "Service", "Pending Docs", "Last Follow-Up", "Action"]
        )
        self.followup_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.followup_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.followup_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.followup_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.followup_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        self.followup_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)
        self.followup_table.setColumnWidth(0, 85)
        self.followup_table.setColumnWidth(2, 140)
        self.followup_table.setColumnWidth(3, 115)
        self.followup_table.setColumnWidth(4, 115)
        self.followup_table.setColumnWidth(5, 200)
        configure_modern_table(self.followup_table)
        self.followup_table.verticalHeader().setDefaultSectionSize(44)
        fu_layout.addWidget(self.followup_table)

        layout.addWidget(self.followup_card)
        self.followup_card.setVisible(False)  # hidden until data found

    def create_kpi_card(self, title: str, value: str, accent_color: str) -> QFrame:
        card = QFrame()
        card.setProperty("class", "card")
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(16, 16, 16, 16)
        c_layout.setSpacing(6)

        t_lbl = QLabel(title)
        t_lbl.setStyleSheet("font-size: 11px; font-weight: 600; color: #64748B; letter-spacing: 0.5px;")
        v_lbl = QLabel(value)
        v_lbl.setObjectName("kpi_value")
        v_lbl.setStyleSheet(f"font-size: 26px; font-weight: 700; color: {accent_color};")

        c_layout.addWidget(t_lbl)
        c_layout.addWidget(v_lbl)
        return card

    def refresh_data(self):
        clients = self.main_window.client_service.search_clients("")
        engagements = self.main_window.engagement_service.list_engagements()

        self.card_clients.findChild(QLabel, "kpi_value").setText(str(len(clients)))
        self.card_engagements.findChild(QLabel, "kpi_value").setText(str(len(engagements)))

        review_count = sum(1 for e in engagements if e.status == EngagementStatus.SUBMITTED_FOR_REVIEW)
        self.card_review_queue.findChild(QLabel, "kpi_value").setText(str(review_count))

        pending_docs = 0
        for eng in engagements:
            summ = self.main_window.engagement_service.get_readiness(eng.engagement_id)
            pending_docs += (summ.mandatory_total - summ.mandatory_accepted)
        self.card_pending_docs.findChild(QLabel, "kpi_value").setText(str(pending_docs))

        # Populate Recent Table with One-Click Dispatch Buttons
        self.table.setRowCount(0)
        for idx, eng in enumerate(engagements[:8]):
            self.table.insertRow(idx)
            self.table.setItem(idx, 0, QTableWidgetItem(f"ENG-{eng.engagement_id:04d}"))
            self.table.setItem(idx, 1, QTableWidgetItem(eng.client_name))

            # Service badge chip
            svc_badge = QLabel(f" {eng.service_name} ")
            svc_badge.setStyleSheet(get_service_badge_style(eng.service_name))
            svc_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge_box = QWidget()
            bb_layout = QHBoxLayout(badge_box)
            bb_layout.setContentsMargins(2, 2, 2, 2)
            bb_layout.addWidget(svc_badge)
            self.table.setCellWidget(idx, 2, badge_box)

            self.table.setItem(idx, 3, QTableWidgetItem(eng.due_date))

            status_text = eng.status.value.replace('_', ' ')
            status_item = QTableWidgetItem(status_text)
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(idx, 4, status_item)

            self.table.setItem(idx, 5, QTableWidgetItem(eng.assigned_name or "Unassigned"))

            # Clean Action Buttons with Windows 11 / macOS styling
            btn_panel = QWidget()
            bp_layout = QHBoxLayout(btn_panel)
            bp_layout.setContentsMargins(6, 4, 6, 4)
            bp_layout.setSpacing(8)

            btn_send = QPushButton("Send Req")
            btn_send.setProperty("class", "btn-table-primary")
            btn_send.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_send.clicked.connect(lambda _, eid=eng.engagement_id: self.open_send_requirements(eid))

            btn_open = QPushButton("Open")
            btn_open.setProperty("class", "btn-table-secondary")
            btn_open.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_open.clicked.connect(lambda _, eid=eng.engagement_id: self.open_in_workspace(eid))

            bp_layout.addWidget(btn_send)
            bp_layout.addWidget(btn_open)
            self.table.setCellWidget(idx, 6, btn_panel)

        # ── Populate Follow-Up Alert table ────────────────────────────────────
        try:
            pending_fus = self.main_window.engagement_repo.list_pending_follow_ups()
        except Exception:
            pending_fus = []

        self.followup_table.setRowCount(0)
        self.followup_card.setVisible(bool(pending_fus))
        for idx, fu_item in enumerate(pending_fus):
            eng = fu_item["engagement"]
            self.followup_table.insertRow(idx)
            self.followup_table.setItem(idx, 0, QTableWidgetItem(f"ENG-{eng.engagement_id:04d}"))
            self.followup_table.setItem(idx, 1, QTableWidgetItem(eng.client_name))

            svc_badge2 = QLabel(f" {eng.service_name} ")
            svc_badge2.setStyleSheet(get_service_badge_style(eng.service_name))
            svc_badge2.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge_box2 = QWidget()
            bb2_layout = QHBoxLayout(badge_box2)
            bb2_layout.setContentsMargins(4, 4, 4, 4)
            bb2_layout.addWidget(svc_badge2)
            self.followup_table.setCellWidget(idx, 2, badge_box2)

            self.followup_table.setItem(idx, 3, QTableWidgetItem(str(fu_item["pending_count"])))
            last_fu = fu_item.get("last_follow_up_date") or "Never"
            self.followup_table.setItem(idx, 4, QTableWidgetItem(str(last_fu)))

            btn_fu = QPushButton("📧 Trigger Follow-Up")
            btn_fu.setProperty("class", "btn-table-primary")
            btn_fu.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_fu.clicked.connect(lambda _, eid=eng.engagement_id: self.trigger_follow_up(eid))
            fu_btn_box = QWidget()
            fu_btn_layout = QHBoxLayout(fu_btn_box)
            fu_btn_layout.setContentsMargins(4, 4, 4, 4)
            fu_btn_layout.addWidget(btn_fu)
            self.followup_table.setCellWidget(idx, 5, fu_btn_box)

    def open_send_requirements(self, engagement_id: int):
        dialog = SendRequirementsDialog(self.main_window, engagement_id=engagement_id, parent=self)
        dialog.exec()
        self.refresh_data()

    def trigger_follow_up(self, engagement_id: int):
        dialog = SendRequirementsDialog(self.main_window, engagement_id=engagement_id, is_follow_up=True, parent=self)
        dialog.exec()
        self.refresh_data()

    def open_multi_service_dispatch(self):
        # Open multi-service dialog
        dialog = SendRequirementsDialog(self.main_window, engagement_id=None, parent=self)
        dialog.exec()

    def open_in_workspace(self, engagement_id: int):
        self.main_window.switch_tab(2)
        self.main_window.workspace_view.select_engagement_by_id(engagement_id)

    def on_row_double_clicked(self, row: int, col: int):
        id_item = self.table.item(row, 0)
        if id_item:
            eng_id = int(id_item.text().replace("ENG-", ""))
            self.open_in_workspace(eng_id)
