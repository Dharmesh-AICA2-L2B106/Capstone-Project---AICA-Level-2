"""License activation and 14-day trial lock enforcement dialog."""

from typing import Optional
from src.clientdesk_ai.ui.qt_compat import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFrame, QMessageBox, QApplication, Qt
)
from src.clientdesk_ai.security.licensing import LicenseService, LicenseInfo
from src.clientdesk_ai.ui.theme import MODERN_QSS


class LicenseActivationDialog(QDialog):
    """Modal dialog displaying trial status and accepting commercial license keys to unlock the system."""

    def __init__(self, license_service: Optional[LicenseService] = None,
                 is_blocking_lock: bool = False, parent=None):
        super().__init__(parent)
        self.license_service = license_service or LicenseService()
        self.is_blocking_lock = is_blocking_lock
        self.unlocked_successfully = False

        self.setWindowTitle("Clientdesk AI — License & Trial Activation")
        self.setMinimumWidth(480)
        self.setStyleSheet(MODERN_QSS)
        self.init_ui()
        self.center_on_screen()

    def center_on_screen(self):
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            w = max(500, self.width())
            h = max(440, self.height())
            x = (geo.width() - w) // 2 + geo.x()
            y = (geo.height() - h) // 2 + geo.y()
            self.setGeometry(x, y, w, h)

    def init_ui(self):
        info = self.license_service.get_license_info()
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)

        card = QFrame()
        card.setStyleSheet(
            "QFrame {"
            "   background-color: #FFFFFF;"
            "   border: 1px solid #CBD5E1;"
            "   border-radius: 10px;"
            "}"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)

        # Header Status Banner
        header_card = QFrame()
        if info.is_locked:
            header_card.setStyleSheet("background-color: #7F1D1D; border-radius: 8px; padding: 12px;")
            title_text = "🔒 System Locked — Trial Period Expired"
            sub_text = info.lock_reason
            status_color = "#FECACA"
        elif info.is_activated:
            header_card.setStyleSheet("background-color: #064E3B; border-radius: 8px; padding: 12px;")
            title_text = "✓ Full Lifetime License Active"
            sub_text = f"Activated with key: {info.license_key}"
            status_color = "#A7F3D0"
        else:
            header_card.setStyleSheet("background-color: #1E293B; border-radius: 8px; padding: 12px;")
            title_text = "Clientdesk AI — 14-Day Free Evaluation Trial"
            sub_text = f"Trial Active: {info.days_remaining} day(s) remaining (Expires {info.expiry_date})"
            status_color = "#38BDF8"

        hb_layout = QVBoxLayout(header_card)
        hb_layout.setContentsMargins(8, 6, 8, 6)
        hb_layout.setSpacing(4)
        hb_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        t_lbl = QLabel(title_text)
        t_lbl.setStyleSheet("color: #FFFFFF; font-size: 15px; font-weight: 700; background: transparent;")
        t_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        s_lbl = QLabel(sub_text)
        s_lbl.setStyleSheet(f"color: {status_color}; font-size: 11.5px; background: transparent;")
        s_lbl.setWordWrap(True)
        s_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        hb_layout.addWidget(t_lbl)
        hb_layout.addWidget(s_lbl)
        layout.addWidget(header_card)

        # Details summary
        details_box = QVBoxLayout()
        details_box.setSpacing(4)
        lbl_info = QLabel("<b>Software Licensing Overview:</b>")
        lbl_info.setStyleSheet("font-size: 12px; color: #0F172A;")
        details_box.addWidget(lbl_info)

        desc = (
            f"• <b>Evaluation Term:</b> 14 Calendar Days<br/>"
            f"• <b>Initial Install Date:</b> {info.start_date}<br/>"
            f"• <b>Trial Expiry Date:</b> {info.expiry_date}<br/>"
            f"• <b>Days Remaining:</b> {info.days_remaining} Day(s)<br/>"
            f"• <b>Access Status:</b> {'🔒 LOCKED' if info.is_locked else 'ACTIVE'}"
        )
        lbl_desc = QLabel(desc)
        lbl_desc.setStyleSheet("font-size: 11.5px; color: #475569; line-height: 1.4;")
        details_box.addWidget(lbl_desc)
        layout.addLayout(details_box)

        # License Key Input Field
        input_box = QVBoxLayout()
        input_box.setSpacing(4)
        lbl_key = QLabel("<b>Enter Commercial License Key: *</b>")
        lbl_key.setStyleSheet("font-size: 12px; color: #0F172A;")

        self.key_edit = QLineEdit()
        self.key_edit.setPlaceholderText("e.g. CDAI-2026-PRO-LIFETIME")
        self.key_edit.setFixedHeight(38)
        self.key_edit.setStyleSheet(
            "QLineEdit {"
            "   background-color: #FFFFFF;"
            "   border: 1.5px solid #CBD5E1;"
            "   border-radius: 6px;"
            "   padding: 4px 10px;"
            "   font-size: 13px;"
            "   font-weight: 600;"
            "   color: #0F172A;"
            "}"
            "QLineEdit:focus {"
            "   border-color: #2563EB;"
            "}"
        )
        self.key_edit.returnPressed.connect(self.handle_activation)
        input_box.addWidget(lbl_key)
        input_box.addWidget(self.key_edit)
        layout.addLayout(input_box)

        # Error / Feedback Label
        self.feedback_lbl = QLabel("")
        self.feedback_lbl.setStyleSheet("font-size: 11.5px; font-weight: 700; padding: 2px 0px;")
        self.feedback_lbl.setWordWrap(True)
        self.feedback_lbl.setVisible(False)
        layout.addWidget(self.feedback_lbl)

        # Action Buttons
        btn_box = QHBoxLayout()
        btn_box.setSpacing(10)

        if self.is_blocking_lock:
            btn_close = QPushButton("Exit Application")
            btn_close.setProperty("class", "btn-secondary")
            btn_close.clicked.connect(self.reject)
        else:
            btn_close = QPushButton("Close")
            btn_close.setProperty("class", "btn-secondary")
            btn_close.clicked.connect(self.reject)

        btn_close.setFixedHeight(38)
        btn_close.setFixedWidth(120)

        self.btn_activate = QPushButton("Activate & Unlock Software →")
        self.btn_activate.setProperty("class", "btn-primary")
        self.btn_activate.setFixedHeight(38)
        self.btn_activate.setStyleSheet("font-weight: 700; font-size: 13px;")
        self.btn_activate.clicked.connect(self.handle_activation)

        btn_box.addWidget(btn_close)
        btn_box.addWidget(self.btn_activate, 1)
        layout.addLayout(btn_box)

        # Policy Notice (Strict 14-day trial only, no public keys given)
        policy_card = QFrame()
        policy_card.setStyleSheet(
            "QFrame {"
            "   background-color: #F8FAFC;"
            "   border: 1px solid #E2E8F0;"
            "   border-radius: 6px;"
            "   padding: 4px;"
            "}"
        )
        pc_layout = QHBoxLayout(policy_card)
        pc_layout.setContentsMargins(10, 8, 10, 8)
        lbl_pc = QLabel(
            "<b>Notice:</b> This software is provided strictly on a 14-day trial basis. "
            "After 14 days, the system locks permanently unless an official developer authorization key is applied."
        )
        lbl_pc.setStyleSheet("font-size: 11px; color: #64748B;")
        lbl_pc.setWordWrap(True)
        pc_layout.addWidget(lbl_pc)
        layout.addWidget(policy_card)
        main_layout.addWidget(card)

        self.key_edit.setFocus()

    def handle_activation(self):
        raw_key = self.key_edit.text().strip()
        ok, msg = self.license_service.activate_license(raw_key)
        if not ok:
            self.feedback_lbl.setText(f"❌ {msg}")
            self.feedback_lbl.setStyleSheet("color: #DC2626; font-size: 11.5px; font-weight: 700;")
            self.feedback_lbl.setVisible(True)
            self.key_edit.selectAll()
            self.key_edit.setFocus()
            return

        self.unlocked_successfully = True
        QMessageBox.information(
            self,
            "License Activated",
            "Software license has been successfully verified and activated.\n\n"
            "Full unlimited lifetime access is now active for Clientdesk AI."
        )
        self.accept()
