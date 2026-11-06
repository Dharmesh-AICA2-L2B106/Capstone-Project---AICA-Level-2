"""Authentication and secure login dialog displayed at application startup."""

from typing import Optional
from src.clientdesk_ai.ui.qt_compat import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFrame, QApplication, Qt
)
from src.clientdesk_ai.domain.models import User
from src.clientdesk_ai.application.services import AuthService
from src.clientdesk_ai.persistence.repositories import UserRepository, LogRepository
from src.clientdesk_ai.ui.theme import MODERN_QSS


class LoginDialog(QDialog):
    """Professional desktop login dialog requiring User ID and Password."""

    def __init__(self, user_repo: Optional[UserRepository] = None,
                 log_repo: Optional[LogRepository] = None, parent=None):
        super().__init__(parent)
        self.user_repo = user_repo or UserRepository()
        self.log_repo = log_repo or LogRepository()
        self.auth_service = AuthService(self.user_repo, self.log_repo)
        self.authenticated_user: Optional[User] = None

        self.setWindowTitle("Clientdesk AI — Firm Authentication")
        self.setMinimumWidth(450)
        self.setStyleSheet(MODERN_QSS)
        self.init_ui()
        self.center_on_screen()

    def center_on_screen(self):
        """Center the login dialog cleanly on the primary monitor."""
        screen = QApplication.primaryScreen()
        if screen:
            screen_geo = screen.availableGeometry()
            dialog_w = max(460, self.width())
            dialog_h = max(560, self.height())
            x = (screen_geo.width() - dialog_w) // 2 + screen_geo.x()
            y = (screen_geo.height() - dialog_h) // 2 + screen_geo.y()
            self.setGeometry(x, y, dialog_w, dialog_h)

    def get_firm_name(self) -> str:
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

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(0)

        # Container Card for clean aesthetic surface
        card = QFrame()
        card.setStyleSheet(
            "QFrame {"
            "   background-color: #FFFFFF;"
            "   border: 1px solid #CBD5E1;"
            "   border-radius: 10px;"
            "}"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(12)

        # Header Branding Card (Deep Royal Navy Header)
        firm_name = self.get_firm_name()
        brand_card = QFrame()
        brand_card.setStyleSheet(
            "QFrame {"
            "   background-color: #1E3A8A;"
            "   border-radius: 8px;"
            "   padding: 12px 14px;"
            "}"
            "QLabel {"
            "   background-color: transparent;"
            "}"
        )
        b_layout = QVBoxLayout(brand_card)
        b_layout.setContentsMargins(6, 6, 6, 6)
        b_layout.setSpacing(4)
        b_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        app_title = QLabel("Clientdesk AI")
        app_title.setStyleSheet("color: #FFFFFF; font-size: 20px; font-weight: 800; letter-spacing: 0.5px;")
        app_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        firm_lbl = QLabel(f"Practice Portal  •  {firm_name}")
        firm_lbl.setStyleSheet("color: #93C5FD; font-size: 13px; font-weight: 700;")
        firm_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        sub_lbl = QLabel("Professional Compliance & Workflow System")
        sub_lbl.setStyleSheet("color: #DBEAFE; font-size: 11px; font-weight: 500;")
        sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        b_layout.addWidget(app_title)
        b_layout.addWidget(firm_lbl)
        b_layout.addWidget(sub_lbl)
        layout.addWidget(brand_card)

        # 14-Day Evaluation Trial & Licensing Indicator
        from src.clientdesk_ai.security.licensing import LicenseService
        lic_service = LicenseService()
        lic_info = lic_service.get_license_info()

        trial_box = QHBoxLayout()
        trial_box.setSpacing(8)
        self.lbl_trial_status = QLabel()
        if lic_info.is_activated:
            self.lbl_trial_status.setText("✓ Commercial Lifetime License Active")
            self.lbl_trial_status.setStyleSheet(
                "color: #065F46; font-size: 11px; font-weight: 700; "
                "background-color: #D1FAE5; border: 1px solid #A7F3D0; "
                "border-radius: 4px; padding: 3px 8px;"
            )
            trial_box.addWidget(self.lbl_trial_status)
        else:
            self.lbl_trial_status.setText(f"🕒 14-Day Evaluation Trial: {lic_info.days_remaining} Days Remaining")
            self.lbl_trial_status.setStyleSheet(
                "color: #92400E; font-size: 11px; font-weight: 700; "
                "background-color: #FEF3C7; border: 1px solid #FDE68A; "
                "border-radius: 4px; padding: 4px 10px;"
            )
            trial_box.addWidget(self.lbl_trial_status)

        trial_box.addStretch()
        layout.addLayout(trial_box)

        # Subtitle Prompt
        login_intro = QLabel("Sign in with your practice credentials to proceed:")
        login_intro.setStyleSheet("color: #334155; font-size: 12px; font-weight: 600; padding-top: 4px;")
        layout.addWidget(login_intro)

        # Form Fields
        form_layout = QVBoxLayout()
        form_layout.setSpacing(10)

        # 1. User ID / Username
        u_box = QVBoxLayout()
        u_box.setSpacing(4)
        u_lbl = QLabel("User ID / Username: *")
        u_lbl.setStyleSheet("font-size: 12px; font-weight: 700; color: #0F172A;")
        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("Enter username (e.g. admin, senior1, staff)")
        self.username_edit.setFixedHeight(36)
        self.username_edit.setStyleSheet(
            "QLineEdit {"
            "   background-color: #FFFFFF;"
            "   border: 1.5px solid #CBD5E1;"
            "   border-radius: 6px;"
            "   padding: 4px 10px;"
            "   font-size: 13px;"
            "   color: #0F172A;"
            "}"
            "QLineEdit:focus {"
            "   border-color: #2563EB;"
            "}"
        )
        self.username_edit.setText("admin")  # Default to admin for convenience
        self.username_edit.returnPressed.connect(self.handle_login)
        u_box.addWidget(u_lbl)
        u_box.addWidget(self.username_edit)
        form_layout.addLayout(u_box)

        # 2. Password
        p_box = QVBoxLayout()
        p_box.setSpacing(4)
        p_lbl = QLabel("Password: *")
        p_lbl.setStyleSheet("font-size: 12px; font-weight: 700; color: #0F172A;")

        p_input_layout = QHBoxLayout()
        p_input_layout.setSpacing(6)
        self.password_edit = QLineEdit()
        self.password_edit.setPlaceholderText("Enter password")
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setFixedHeight(36)
        self.password_edit.setStyleSheet(
            "QLineEdit {"
            "   background-color: #FFFFFF;"
            "   border: 1.5px solid #CBD5E1;"
            "   border-radius: 6px;"
            "   padding: 4px 10px;"
            "   font-size: 13px;"
            "   color: #0F172A;"
            "}"
            "QLineEdit:focus {"
            "   border-color: #2563EB;"
            "}"
        )
        self.password_edit.setText("admin")  # Default password matching admin
        self.password_edit.returnPressed.connect(self.handle_login)

        self.btn_toggle_pw = QPushButton("Show")
        self.btn_toggle_pw.setToolTip("Show / Hide password")
        self.btn_toggle_pw.setFixedSize(54, 36)
        self.btn_toggle_pw.setProperty("class", "btn-secondary")
        self.btn_toggle_pw.setStyleSheet(
            "QPushButton {"
            "   background-color: #F1F5F9;"
            "   border: 1.5px solid #CBD5E1;"
            "   border-radius: 6px;"
            "   font-size: 11px;"
            "   font-weight: 700;"
            "   color: #475569;"
            "}"
            "QPushButton:hover {"
            "   background-color: #E2E8F0;"
            "   color: #0F172A;"
            "}"
        )
        self.btn_toggle_pw.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_pw.clicked.connect(self.toggle_password_visibility)

        p_input_layout.addWidget(self.password_edit, 1)
        p_input_layout.addWidget(self.btn_toggle_pw)

        p_box.addWidget(p_lbl)
        p_box.addLayout(p_input_layout)
        form_layout.addLayout(p_box)

        layout.addLayout(form_layout)

        # Error / Feedback Message Label
        self.error_lbl = QLabel("")
        self.error_lbl.setStyleSheet(
            "color: #DC2626; font-size: 11.5px; font-weight: 700; padding: 2px 0px;"
        )
        self.error_lbl.setWordWrap(True)
        self.error_lbl.setVisible(False)
        layout.addWidget(self.error_lbl)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        btn_exit = QPushButton("Exit")
        btn_exit.setProperty("class", "btn-secondary")
        btn_exit.setFixedHeight(38)
        btn_exit.setFixedWidth(90)
        btn_exit.clicked.connect(self.reject)

        self.btn_signin = QPushButton("Sign In →")
        self.btn_signin.setProperty("class", "btn-primary")
        self.btn_signin.setFixedHeight(38)
        self.btn_signin.setStyleSheet("font-weight: 700; font-size: 13.5px; padding: 6px 20px;")
        self.btn_signin.clicked.connect(self.handle_login)

        btn_layout.addWidget(btn_exit)
        btn_layout.addWidget(self.btn_signin, 1)
        layout.addLayout(btn_layout)

        # Practice Accounts Quick Fill Pill
        helper_card = QFrame()
        helper_card.setStyleSheet(
            "QFrame {"
            "   background-color: #F8FAFC;"
            "   border: 1px solid #E2E8F0;"
            "   border-radius: 6px;"
            "   padding: 4px;"
            "}"
        )
        h_layout = QVBoxLayout(helper_card)
        h_layout.setContentsMargins(8, 6, 8, 6)
        h_layout.setSpacing(4)

        h_title = QLabel("Default Admin: ID 'admin' | PW 'admin' • Staff PW set by Admin:")
        h_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #475569;")
        h_layout.addWidget(h_title)

        chips_box = QHBoxLayout()
        chips_box.setSpacing(6)

        btn_chip_admin = QPushButton("Admin (Full Access)")
        btn_chip_admin.setProperty("class", "btn-secondary")
        btn_chip_admin.setStyleSheet("font-size: 11px; font-weight: 700; color: #1D4ED8; padding: 3px 8px;")
        btn_chip_admin.clicked.connect(lambda: self.prefill_credentials("admin", "admin"))

        btn_chip_staff = QPushButton("Staff Operator")
        btn_chip_staff.setProperty("class", "btn-secondary")
        btn_chip_staff.setStyleSheet("font-size: 11px; font-weight: 600; padding: 3px 8px;")
        btn_chip_staff.clicked.connect(lambda: self.prefill_credentials("staff", "staff"))

        btn_chip_senior = QPushButton("Senior Reviewer")
        btn_chip_senior.setProperty("class", "btn-secondary")
        btn_chip_senior.setStyleSheet("font-size: 11px; font-weight: 600; padding: 3px 8px;")
        btn_chip_senior.clicked.connect(lambda: self.prefill_credentials("senior", "senior"))

        chips_box.addWidget(btn_chip_admin)
        chips_box.addWidget(btn_chip_staff)
        chips_box.addWidget(btn_chip_senior)
        chips_box.addStretch()
        h_layout.addLayout(chips_box)

        layout.addWidget(helper_card)
        main_layout.addWidget(card)

        self.password_edit.setFocus()

    def prefill_credentials(self, username: str, password: str):
        self.username_edit.setText(username)
        self.password_edit.setText(password)
        self.error_lbl.setVisible(False)
        self.password_edit.setFocus()

    def toggle_password_visibility(self):
        if self.password_edit.echoMode() == QLineEdit.EchoMode.Password:
            self.password_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self.btn_toggle_pw.setText("Hide")
        else:
            self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.btn_toggle_pw.setText("Show")

    def open_license_dialog(self):
        from src.clientdesk_ai.ui.views.license_dialog import LicenseActivationDialog
        from src.clientdesk_ai.security.licensing import LicenseService
        lic_service = LicenseService()
        dlg = LicenseActivationDialog(license_service=lic_service, is_blocking_lock=False, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            info = lic_service.get_license_info()
            if info.is_activated:
                self.lbl_trial_status.setText("✓ Commercial Lifetime License Active")
                self.lbl_trial_status.setStyleSheet(
                    "color: #065F46; font-size: 11px; font-weight: 700; "
                    "background-color: #D1FAE5; border: 1px solid #A7F3D0; "
                    "border-radius: 4px; padding: 3px 8px;"
                )

    def handle_login(self):
        # 1. Enforce 14-day trial lock on login
        from src.clientdesk_ai.security.licensing import LicenseService
        lic_service = LicenseService()
        info = lic_service.get_license_info()
        if info.is_locked:
            from src.clientdesk_ai.ui.views.license_dialog import LicenseActivationDialog
            dlg = LicenseActivationDialog(license_service=lic_service, is_blocking_lock=True, parent=self)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return

        username = self.username_edit.text().strip()
        password = self.password_edit.text().strip()

        if not username:
            self.error_lbl.setText("Please enter your User ID / Username.")
            self.error_lbl.setVisible(True)
            self.username_edit.setFocus()
            return

        if not password:
            self.error_lbl.setText("Please enter your password.")
            self.error_lbl.setVisible(True)
            self.password_edit.setFocus()
            return

        ok, user, msg = self.auth_service.authenticate(username, password)
        if not ok or not user:
            self.error_lbl.setText(f"{msg}")
            self.error_lbl.setVisible(True)
            self.password_edit.selectAll()
            self.password_edit.setFocus()
            return

        self.authenticated_user = user
        self.accept()
