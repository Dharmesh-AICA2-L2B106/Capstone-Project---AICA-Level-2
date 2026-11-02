"""Main application window with modern sidebar navigation and coordinated views."""

import sys
from typing import Optional

from src.clientdesk_ai.ui.qt_compat import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QStackedWidget, QFrame, QButtonGroup, QDialog, QMessageBox, QSize, Qt,
    QComboBox, QIcon, QPainter, QPen, QColor, QPixmap
)
from src.clientdesk_ai.ui.theme import MODERN_QSS
from src.clientdesk_ai.ui.views.dashboard_view import DashboardView
from src.clientdesk_ai.ui.views.clients_view import ClientsView
from src.clientdesk_ai.ui.views.engagement_workspace_view import EngagementWorkspaceView
from src.clientdesk_ai.ui.views.review_queue_view import ReviewQueueView
from src.clientdesk_ai.ui.views.templates_view import TemplatesView
from src.clientdesk_ai.ui.views.knowledge_view import KnowledgeView
from src.clientdesk_ai.ui.views.reports_view import ReportsView
from src.clientdesk_ai.ui.views.settings_view import SettingsView

from src.clientdesk_ai.domain.models import User, UserRole
from src.clientdesk_ai.persistence.repositories import (
    UserRepository, ClientRepository, TemplateRepository, EngagementRepository,
    AttachmentRepository, LogRepository, KnowledgeRepository
)
from src.clientdesk_ai.application.services import (
    AuthService, ClientService, EngagementService, ChecklistService,
    AttachmentService, KnowledgeSearchService, EmailService
)


class MainWindow(QMainWindow):
    def __init__(self, current_user: Optional[User] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Clientdesk AI — Client & Service Workflow Management")
        self.resize(1360, 850)
        self.setMinimumSize(1280, 800)

        # Repositories & Services
        self.user_repo = UserRepository()
        self.client_repo = ClientRepository()
        self.template_repo = TemplateRepository()
        self.engagement_repo = EngagementRepository()
        self.attachment_repo = AttachmentRepository()
        self.log_repo = LogRepository()
        self.knowledge_repo = KnowledgeRepository()

        self.auth_service = AuthService(self.user_repo, self.log_repo)
        self.client_service = ClientService(self.client_repo, self.log_repo)
        self.engagement_service = EngagementService(self.engagement_repo, self.template_repo, self.log_repo)
        self.checklist_service = ChecklistService(self.engagement_repo, self.log_repo)
        self.attachment_service = AttachmentService(self.attachment_repo, self.log_repo)
        self.search_service = KnowledgeSearchService()
        self.email_service = EmailService()

        # Default to admin user if not passed
        self.current_user = current_user or self.user_repo.get_by_username("admin") or User(
            user_id=1, username="admin", full_name="Default Administrator", role=UserRole.ADMIN
        )

        self.init_ui()
        self.apply_role_permissions()
        self.setStyleSheet(MODERN_QSS)

    def init_ui(self):
        main_widget = QWidget()
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Left Sidebar
        self.sidebar = QWidget()
        self.sidebar.setObjectName("SidebarWidget")
        self.sidebar.setFixedWidth(250)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(16, 10, 16, 16)
        sidebar_layout.setSpacing(4)

        # App Brand
        brand_title = QLabel("Clientdesk AI")
        brand_title.setObjectName("SidebarTitle")
        self.sidebar_firm_lbl = QLabel(self.get_firm_name())
        self.sidebar_firm_lbl.setObjectName("SidebarFirmLabel")
        self.sidebar_firm_lbl.setStyleSheet(
            "color: #93C5FD; font-size: 13px; font-weight: 700; padding: 0px 4px 4px 4px;"
        )
        brand_sub = QLabel("Professional Workflow v1.1")
        brand_sub.setObjectName("SidebarSubtitle")
        sidebar_layout.addWidget(brand_title)
        sidebar_layout.addWidget(self.sidebar_firm_lbl)
        sidebar_layout.addWidget(brand_sub)

        # Navigation Buttons Group
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)

        nav_items = [
            ("Dashboard", 0),
            ("Client Master", 1),
            ("Workspaces & Checklists", 2),
            ("Senior Review Queue", 3),
            ("Service Catalogue (6)", 4),
            ("SOP Knowledge Search", 5),
            ("Reports & Exports", 6),
            ("Settings & Diagnostics", 7),
        ]

        for text, index in nav_items:
            btn = QPushButton(text)
            btn.setProperty("class", "nav-btn")
            btn.setCheckable(True)
            if index == 0:
                btn.setChecked(True)
            btn.clicked.connect(lambda checked, idx=index: self.switch_tab(idx))
            self.nav_group.addButton(btn, index)
            sidebar_layout.addWidget(btn)

        # Apply Role Security Matrix (Admin controls all panels; Staff/Reviewer access designated panels)
        self.apply_role_permissions()

        sidebar_layout.addStretch()

        # Developer Attribution on Left Bottom (Requested: Murtaza Davawala)
        dev_card = QFrame()
        dev_card.setObjectName("SidebarDevCard")
        dev_card.setStyleSheet(
            "QFrame#SidebarDevCard {"
            "   background-color: #172554;"
            "   border: 1px solid #2563EB;"
            "   border-radius: 6px;"
            "   margin: 4px 0px 4px 0px;"
            "   padding: 10px 12px;"
            "}"
            "QFrame#SidebarDevCard QLabel {"
            "   border: none;"
            "   background: transparent;"
            "   padding: 0px;"
            "   margin: 0px;"
            "}"
        )
        dev_layout = QVBoxLayout(dev_card)
        dev_layout.setContentsMargins(4, 4, 4, 4)
        dev_layout.setSpacing(3)

        lbl_dev_by = QLabel("DEVELOPED BY")
        lbl_dev_by.setStyleSheet(
            "font-size: 10px; font-weight: 700; color: #93C5FD; letter-spacing: 0.8px; border: none; background: transparent;"
        )
        lbl_dev_name = QLabel("Murtaza Davawala")
        lbl_dev_name.setStyleSheet(
            "font-size: 13.5px; font-weight: 700; color: #FFFFFF; border: none; background: transparent;"
        )
        dev_layout.addWidget(lbl_dev_by)
        dev_layout.addWidget(lbl_dev_name)
        sidebar_layout.addWidget(dev_card)

        main_layout.addWidget(self.sidebar)

        # 2. Right Content Area (Top bar + Stacked Views)
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # Top Bar
        top_bar = QWidget()
        top_bar.setObjectName("TopBarWidget")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(16, 10, 24, 10)
        top_layout.setSpacing(12)

        self.btn_toggle_sidebar = QPushButton()
        self.btn_toggle_sidebar.setObjectName("BtnToggleSidebar")
        self.btn_toggle_sidebar.setToolTip("Show / Hide Sidebar Navigation (Ctrl+B)")
        self.btn_toggle_sidebar.setFixedSize(36, 36)
        self.btn_toggle_sidebar.setIcon(self._create_hamburger_icon())
        self.btn_toggle_sidebar.setIconSize(QSize(20, 20))
        self.btn_toggle_sidebar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_sidebar.setStyleSheet(
            "QPushButton#BtnToggleSidebar {"
            "   background-color: #FFFFFF;"
            "   border: 1px solid #CBD5E1;"
            "   border-bottom: 2px solid #94A3B8;"
            "   border-radius: 6px;"
            "   padding: 0px;"
            "}"
            "QPushButton#BtnToggleSidebar:hover {"
            "   background-color: #F1F5F9;"
            "   border-color: #94A3B8;"
            "}"
        )
        self.btn_toggle_sidebar.clicked.connect(self.toggle_sidebar)
        top_layout.addWidget(self.btn_toggle_sidebar)

        self.page_title = QLabel("Dashboard")
        self.page_title.setObjectName("PageTitle")
        top_layout.addWidget(self.page_title)

        # Firm Name Branding Badge (Displayed on Every Page)
        self.firm_badge = QLabel()
        self.firm_badge.setObjectName("TopBarFirmBadge")
        top_layout.addWidget(self.firm_badge)
        self.update_firm_display()

        # License & 14-Day Trial Status Badge
        self.license_badge = QPushButton()
        self.license_badge.setObjectName("TopBarLicenseBadge")
        self.license_badge.setFixedHeight(28)
        self.license_badge.setCursor(Qt.CursorShape.PointingHandCursor)
        self.license_badge.clicked.connect(self.open_license_dialog)
        top_layout.addWidget(self.license_badge)
        self.update_license_display()

        top_layout.addStretch()

        # User Profile, Role Badge, and Secure Switch / Sign Out Button
        self.role_badge = QLabel()
        self.role_badge.setObjectName("TopBarRoleBadge")

        self.user_info_lbl = QLabel()
        self.user_info_lbl.setObjectName("TopBarUserInfoLabel")
        self.user_info_lbl.setStyleSheet(
            "font-size: 12.5px; font-weight: 600; color: #1E293B; margin-right: 6px;"
        )

        self.btn_switch_user = QPushButton("🚪 Switch / Sign Out")
        self.btn_switch_user.setProperty("class", "btn-secondary")
        self.btn_switch_user.setFixedHeight(30)
        self.btn_switch_user.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_switch_user.setToolTip("Sign out and log in as another staff member or Administrator with password")
        self.btn_switch_user.setStyleSheet(
            "font-size: 11.5px; font-weight: 600; color: #DC2626; padding: 2px 10px;"
        )
        self.btn_switch_user.clicked.connect(self.handle_switch_user)

        # Retain hidden user_switcher object for backwards compatibility
        self.user_switcher = QComboBox()
        self.user_switcher.setVisible(False)
        self.populate_user_switcher()

        self.update_current_user_display()

        top_layout.addWidget(self.user_info_lbl)
        top_layout.addWidget(self.role_badge)
        top_layout.addWidget(self.btn_switch_user)
        right_layout.addWidget(top_bar)

        # Stacked Views
        self.stacked_widget = QStackedWidget()

        self.dashboard_view = DashboardView(self)
        self.clients_view = ClientsView(self)
        self.workspace_view = EngagementWorkspaceView(self)
        self.review_view = ReviewQueueView(self)
        self.templates_view = TemplatesView(self)
        self.knowledge_view = KnowledgeView(self)
        self.reports_view = ReportsView(self)
        self.settings_view = SettingsView(self)

        self.stacked_widget.addWidget(self.dashboard_view)
        self.stacked_widget.addWidget(self.clients_view)
        self.stacked_widget.addWidget(self.workspace_view)
        self.stacked_widget.addWidget(self.review_view)
        self.stacked_widget.addWidget(self.templates_view)
        self.stacked_widget.addWidget(self.knowledge_view)
        self.stacked_widget.addWidget(self.reports_view)
        self.stacked_widget.addWidget(self.settings_view)

        right_layout.addWidget(self.stacked_widget)
        main_layout.addWidget(right_container)

        self.setCentralWidget(main_widget)
        self.switch_tab(0)

    def switch_tab(self, index: int):
        titles = [
            "Dashboard", "Client Master", "Workspaces & Checklists",
            "Senior Review Queue", "Service Catalogue (6 Approved Groups)",
            "SOP Knowledge Search", "Reports & Exports", "Settings & Diagnostics"
        ]
        self.stacked_widget.setCurrentIndex(index)
        self.page_title.setText(titles[index])

        target_btn = self.nav_group.button(index)
        for btn in self.nav_group.buttons():
            is_active = (btn == target_btn)
            btn.setChecked(is_active)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

        current_view = self.stacked_widget.currentWidget()
        if hasattr(current_view, "refresh_data"):
            current_view.refresh_data()

    def toggle_sidebar(self):
        """Toggle left navigation sidebar visibility."""
        is_visible = self.sidebar.isVisible()
        self.sidebar.setVisible(not is_visible)

    def get_firm_name(self) -> str:
        """Fetch the statutory practice / firm name from organisation_profile."""
        try:
            from src.clientdesk_ai.persistence.database import get_db_connection
            conn = get_db_connection()
            row = conn.execute("SELECT firm_name FROM organisation_profile LIMIT 1;").fetchone()
            conn.close()
            if row and row["firm_name"] and row["firm_name"].strip():
                return row["firm_name"].strip()
        except Exception:
            pass
        return "XYZ and Co"

    def update_firm_display(self):
        """Update firm branding across window title, header bar, and sidebar."""
        firm = self.get_firm_name()
        if hasattr(self, "firm_badge"):
            self.firm_badge.setText(f"🏢  {firm}")
            self.firm_badge.setStyleSheet(
                "background-color: #F1F5F9; color: #0F172A; font-weight: 700; font-size: 13px; "
                "border: 1px solid #CBD5E1; border-radius: 6px; padding: 4px 12px; margin-left: 10px;"
            )
        if hasattr(self, "sidebar_firm_lbl"):
            self.sidebar_firm_lbl.setText(firm)
        self.setWindowTitle(f"Clientdesk AI  —  {firm}")

    def update_license_display(self):
        """Refresh top-bar trial countdown and license status badge."""
        if not hasattr(self, "license_badge"):
            return
        from src.clientdesk_ai.security.licensing import LicenseService
        lic_service = LicenseService()
        info = lic_service.get_license_info()
        if info.is_activated:
            self.license_badge.setText("✓ Licensed")
            self.license_badge.setToolTip("Full Commercial Lifetime License Active")
            self.license_badge.setStyleSheet(
                "QPushButton#TopBarLicenseBadge {"
                "   background-color: #ECFDF5; color: #047857; font-weight: 700; font-size: 11px;"
                "   border: 1px solid #A7F3D0; border-radius: 6px; padding: 2px 10px; margin-left: 8px;"
                "}"
                "QPushButton#TopBarLicenseBadge:hover {"
                "   background-color: #D1FAE5;"
                "}"
            )
        elif info.is_locked:
            self.license_badge.setText("🔒 Trial Expired")
            self.license_badge.setToolTip("14-Day Free Trial Expired. System is locked. Click to activate key.")
            self.license_badge.setStyleSheet(
                "QPushButton#TopBarLicenseBadge {"
                "   background-color: #FEE2E2; color: #B91C1C; font-weight: 700; font-size: 11px;"
                "   border: 1px solid #FECACA; border-radius: 6px; padding: 2px 10px; margin-left: 8px;"
                "}"
            )
        else:
            self.license_badge.setText(f"🕒 Trial: {info.days_remaining}d Left")
            self.license_badge.setToolTip(f"14-Day Evaluation Trial (Expires {info.expiry_date}). System locks automatically after 14 days.")
            self.license_badge.setStyleSheet(
                "QPushButton#TopBarLicenseBadge {"
                "   background-color: #FFFBEB; color: #B45309; font-weight: 700; font-size: 11px;"
                "   border: 1px solid #FDE68A; border-radius: 6px; padding: 2px 10px; margin-left: 8px;"
                "}"
                "QPushButton#TopBarLicenseBadge:hover {"
                "   background-color: #FEF3C7;"
                "}"
            )

    def open_license_dialog(self):
        """Open license key activation dialog."""
        from src.clientdesk_ai.ui.views.license_dialog import LicenseActivationDialog
        from src.clientdesk_ai.security.licensing import LicenseService
        lic_service = LicenseService()
        info = lic_service.get_license_info()
        dlg = LicenseActivationDialog(license_service=lic_service, is_blocking_lock=info.is_locked, parent=self)
        dlg.exec()
        self.update_license_display()
        if hasattr(self, "settings_view") and hasattr(self.settings_view, "refresh_license_display"):
            self.settings_view.refresh_license_display()

    def _create_hamburger_icon(self) -> QIcon:
        """Render a clean 3-line hamburger icon without font or unicode dependencies."""
        pixmap = QPixmap(24, 24)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(QColor("#1E293B"))
        pen.setWidth(2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)

        margin = 4
        painter.drawLine(margin, 6, 24 - margin, 6)
        painter.drawLine(margin, 12, 24 - margin, 12)
        painter.drawLine(margin, 18, 24 - margin, 18)
        painter.end()
        return QIcon(pixmap)

    def populate_user_switcher(self):
        """Populate top-bar user switcher with all available practice users."""
        self.user_switcher.blockSignals(True)
        self.user_switcher.clear()
        try:
            users = self.user_repo.list_all()
            for u in users:
                label = f"{u.full_name} ({u.role.value})"
                self.user_switcher.addItem(label, u.user_id)
                if self.current_user and u.user_id == self.current_user.user_id:
                    self.user_switcher.setCurrentIndex(self.user_switcher.count() - 1)
        except Exception:
            pass
        self.user_switcher.blockSignals(False)

    def apply_role_permissions(self):
        """Configure sidebar navigation buttons and panel permissions based on the active user's role."""
        if not self.current_user:
            return

        is_admin = (self.current_user.role == UserRole.ADMIN)
        is_senior_or_partner = (self.current_user.role in (UserRole.SENIOR, UserRole.PARTNER, UserRole.ADMIN))

        # Tab 3: Senior Review Queue - visible only to Senior, Partner, Admin (4-Eyes principle)
        if hasattr(self, "nav_group"):
            btn_review = self.nav_group.button(3)
            if btn_review:
                btn_review.setVisible(is_senior_or_partner)

            # Tab 7: Settings & Diagnostics (User management & system setup) - Admin only has full power to control
            btn_settings = self.nav_group.button(7)
            if btn_settings:
                btn_settings.setVisible(is_admin)

        # If current active tab was hidden by role, redirect to Dashboard (0)
        if hasattr(self, "stacked_widget"):
            current_idx = self.stacked_widget.currentIndex()
            if (current_idx == 3 and not is_senior_or_partner) or (current_idx == 7 and not is_admin):
                self.switch_tab(0)

    def handle_switch_user(self):
        """Prompt for credentials to switch user securely. Staff cannot impersonate Admin without admin password."""
        from src.clientdesk_ai.ui.views.login_dialog import LoginDialog
        login_dlg = LoginDialog(parent=self)
        if login_dlg.exec() == QDialog.DialogCode.Accepted and login_dlg.authenticated_user:
            self.current_user = login_dlg.authenticated_user
            self.update_current_user_display()
            self.apply_role_permissions()
            current_view = self.stacked_widget.currentWidget()
            if hasattr(current_view, "refresh_data"):
                current_view.refresh_data()

    def on_user_switched(self, index: int):
        """Handle switching the active user profile across the application."""
        user_id = self.user_switcher.currentData()
        if not user_id:
            return
        user = self.user_repo.get_by_id(user_id)
        if user:
            self.current_user = user
            self.update_current_user_display()
            self.apply_role_permissions()
            current_view = self.stacked_widget.currentWidget()
            if hasattr(current_view, "refresh_data"):
                current_view.refresh_data()

    def update_current_user_display(self):
        """Update role badge and user identity display based on active user's permissions."""
        if not hasattr(self, "role_badge") or not self.current_user:
            return
        role_val = self.current_user.role.value if hasattr(self.current_user.role, "value") else str(self.current_user.role)
        role_colors = {
            "ADMIN": ("#DBEAFE", "#1D4ED8"),
            "PARTNER": ("#EDE9FE", "#6D28D9"),
            "SENIOR": ("#FEF3C7", "#92400E"),
            "STAFF": ("#DCFCE7", "#15803D"),
            "READ_ONLY": ("#F1F5F9", "#475569"),
        }
        bg, text_color = role_colors.get(role_val, ("#DBEAFE", "#1D4ED8"))
        self.role_badge.setText(f" {role_val} ")
        self.role_badge.setStyleSheet(
            f"background-color: {bg}; color: {text_color}; font-weight: 700; "
            f"font-size: 11px; border-radius: 4px; padding: 3px 8px; margin-right: 4px;"
        )
        if hasattr(self, "user_info_lbl"):
            self.user_info_lbl.setText(f"👤 {self.current_user.full_name} ({self.current_user.username})")
