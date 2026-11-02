"""Organization settings, system diagnostics, and offline backup generator."""

import shutil
import sqlite3
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from src.clientdesk_ai.ui.qt_compat import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFrame, QGridLayout, QMessageBox, QFileDialog, QTableWidget, QTableWidgetItem,
    QHeaderView, QComboBox, QDialog, QScrollArea, QCheckBox, Qt
)
from src.clientdesk_ai.domain.models import User, UserRole
from src.clientdesk_ai.ui.theme import configure_modern_table
from src.clientdesk_ai.security.crypto import hash_password
from src.clientdesk_ai.config.settings import CONFIG
from src.clientdesk_ai.persistence.database import get_db_connection


class SettingsView(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Smooth scrolling wrapper so settings cards never compress on smaller screens
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(20)

        # Header
        title_box = QVBoxLayout()
        title_lbl = QLabel("Organization Profile & System Diagnostics")
        title_lbl.setStyleSheet("font-size: 20px; font-weight: 700; color: #0F172A;")
        sub_lbl = QLabel("Manage local professional firm details, inspect database engine health, and generate backups.")
        sub_lbl.setStyleSheet("font-size: 13px; color: #64748B;")
        title_box.addWidget(title_lbl)
        title_box.addWidget(sub_lbl)
        layout.addLayout(title_box)

        # 1. Organization Profile Card
        org_card = QFrame()
        org_card.setProperty("class", "card")
        org_layout = QVBoxLayout(org_card)
        org_layout.setContentsMargins(18, 18, 18, 18)
        org_layout.setSpacing(14)

        org_title = QLabel("Local Firm Organization Identity (Configurable)")
        org_title.setStyleSheet("font-size: 15px; font-weight: 600; color: #0F172A;")
        org_layout.addWidget(org_title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(12)
        grid.setColumnMinimumWidth(0, 180)
        grid.setColumnStretch(1, 1)

        self.firm_name_edit = QLineEdit()
        self.firm_name_edit.setMinimumHeight(36)
        self.firm_name_edit.setPlaceholderText("e.g. Veritas Tax Advisors & Associates")

        self.tagline_edit = QLineEdit()
        self.tagline_edit.setMinimumHeight(36)
        self.tagline_edit.setPlaceholderText("e.g. Chartered Accountants & Tax Consultants")

        self.address_edit = QLineEdit()
        self.address_edit.setMinimumHeight(36)
        self.address_edit.setPlaceholderText("Firm Principal Office Address")

        self.email_edit = QLineEdit()
        self.email_edit.setMinimumHeight(36)
        self.email_edit.setPlaceholderText("contact@firmdomain.com")

        self.phone_edit = QLineEdit()
        self.phone_edit.setMinimumHeight(36)
        self.phone_edit.setPlaceholderText("+91 Office Landline / Phone")

        lbl_fn = QLabel("Firm / Practice Name:")
        lbl_fn.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(lbl_fn, 0, 0)
        grid.addWidget(self.firm_name_edit, 0, 1)

        lbl_tl = QLabel("Professional Tagline:")
        lbl_tl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(lbl_tl, 1, 0)
        grid.addWidget(self.tagline_edit, 1, 1)

        lbl_ad = QLabel("Office Address:")
        lbl_ad.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(lbl_ad, 2, 0)
        grid.addWidget(self.address_edit, 2, 1)

        lbl_em = QLabel("Official Email:")
        lbl_em.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(lbl_em, 3, 0)
        grid.addWidget(self.email_edit, 3, 1)

        lbl_ph = QLabel("Telephone / Phone:")
        lbl_ph.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(lbl_ph, 4, 0)
        grid.addWidget(self.phone_edit, 4, 1)

        org_layout.addLayout(grid)

        btn_save_org = QPushButton("Save Organization Identity")
        btn_save_org.setProperty("class", "btn-primary")
        btn_save_org.setMinimumHeight(36)
        btn_save_org.clicked.connect(self.save_org_profile)
        org_layout.addWidget(btn_save_org, alignment=Qt.AlignmentFlag.AlignRight)

        layout.addWidget(org_card)

        # 2. Email / SMTP Configuration Card
        smtp_card = QFrame()
        smtp_card.setProperty("class", "card")
        smtp_layout = QVBoxLayout(smtp_card)
        smtp_layout.setContentsMargins(18, 18, 18, 18)
        smtp_layout.setSpacing(14)

        smtp_title = QLabel("Email / SMTP Configuration")
        smtp_title.setStyleSheet("font-size: 15px; font-weight: 600; color: #0F172A;")
        smtp_layout.addWidget(smtp_title)

        smtp_desc = QLabel(
            "Configure outbound SMTP email settings for direct checklist dispatch to clients. "
            "App Passwords are encrypted and saved in the local Windows Credential Manager via Keyring."
        )
        smtp_desc.setStyleSheet("color: #64748B; font-size: 12px;")
        smtp_desc.setWordWrap(True)
        smtp_layout.addWidget(smtp_desc)

        s_grid = QGridLayout()
        s_grid.setHorizontalSpacing(16)
        s_grid.setVerticalSpacing(12)
        s_grid.setColumnMinimumWidth(0, 180)
        s_grid.setColumnStretch(1, 1)

        self.smtp_host_edit = QLineEdit()
        self.smtp_host_edit.setMinimumHeight(36)
        self.smtp_host_edit.setPlaceholderText("e.g. smtp.gmail.com or smtp.office365.com")

        self.smtp_port_edit = QLineEdit()
        self.smtp_port_edit.setMinimumHeight(36)
        self.smtp_port_edit.setPlaceholderText("587 (TLS/STARTTLS) or 465 (SSL)")

        self.smtp_user_edit = QLineEdit()
        self.smtp_user_edit.setMinimumHeight(36)
        self.smtp_user_edit.setPlaceholderText("sender@firmdomain.com or your_email@gmail.com")

        self.smtp_pass_edit = QLineEdit()
        self.smtp_pass_edit.setMinimumHeight(36)
        self.smtp_pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.smtp_pass_edit.setPlaceholderText("Enter 16-character App Password (Leave blank to keep existing)")

        self.smtp_tls_chk = QCheckBox("Use STARTTLS / TLS Encryption (Default for port 587)")
        self.smtp_tls_chk.setChecked(True)

        lbl_sh = QLabel("SMTP Host:")
        lbl_sh.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        s_grid.addWidget(lbl_sh, 0, 0)
        s_grid.addWidget(self.smtp_host_edit, 0, 1)

        lbl_sp = QLabel("SMTP Port:")
        lbl_sp.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        s_grid.addWidget(lbl_sp, 1, 0)
        s_grid.addWidget(self.smtp_port_edit, 1, 1)

        lbl_su = QLabel("Sender Email Address:")
        lbl_su.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        s_grid.addWidget(lbl_su, 2, 0)
        s_grid.addWidget(self.smtp_user_edit, 2, 1)

        lbl_pw = QLabel("App Password / Password:")
        lbl_pw.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        s_grid.addWidget(lbl_pw, 3, 0)
        s_grid.addWidget(self.smtp_pass_edit, 3, 1)

        s_grid.addWidget(self.smtp_tls_chk, 4, 1)
        smtp_layout.addLayout(s_grid)

        btn_save_smtp = QPushButton("Save Email Settings")
        btn_save_smtp.setProperty("class", "btn-primary")
        btn_save_smtp.setMinimumHeight(36)
        btn_save_smtp.clicked.connect(self.save_email_settings)
        smtp_layout.addWidget(btn_save_smtp, alignment=Qt.AlignmentFlag.AlignRight)

        layout.addWidget(smtp_card)

        # 3. System Diagnostics & Backup Card
        diag_card = QFrame()
        diag_card.setProperty("class", "card")
        diag_layout = QVBoxLayout(diag_card)
        diag_layout.setContentsMargins(18, 18, 18, 18)
        diag_layout.setSpacing(14)

        diag_title = QLabel("Database Engine Diagnostics & Offline Backup")
        diag_title.setStyleSheet("font-size: 15px; font-weight: 600; color: #0F172A;")
        diag_layout.addWidget(diag_title)

        d_grid = QGridLayout()
        d_grid.setHorizontalSpacing(16)
        d_grid.setVerticalSpacing(12)
        d_grid.setColumnMinimumWidth(0, 180)
        d_grid.setColumnStretch(1, 1)

        py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        lbl_pr = QLabel("Python Runtime:")
        lbl_pr.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        d_grid.addWidget(lbl_pr, 0, 0)
        val_pr = QLabel(f"<b>Python {py_ver} (64-bit Windows)</b>")
        val_pr.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        d_grid.addWidget(val_pr, 0, 1)

        lbl_de = QLabel("Database Engine:")
        lbl_de.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        d_grid.addWidget(lbl_de, 1, 0)
        val_de = QLabel(f"<b>SQLite {sqlite3.sqlite_version} (WAL Mode Active, FTS5 Enabled)</b>")
        val_de.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        d_grid.addWidget(val_de, 1, 1)

        lbl_da = QLabel("Deployment Architecture:")
        lbl_da.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        d_grid.addWidget(lbl_da, 2, 0)
        val_da = QLabel("<b>Mode A — Single Windows PC (100% Offline)</b>")
        val_da.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        d_grid.addWidget(val_da, 2, 1)

        lbl_db = QLabel("Local Database Path:")
        lbl_db.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        d_grid.addWidget(lbl_db, 3, 0)
        val_db = QLabel(f"<code>{CONFIG.db_path}</code>")
        val_db.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        d_grid.addWidget(val_db, 3, 1)

        lbl_fs = QLabel("Managed File Store:")
        lbl_fs.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        d_grid.addWidget(lbl_fs, 4, 0)
        val_fs = QLabel(f"<code>{CONFIG.filestore_path}</code>")
        val_fs.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        d_grid.addWidget(val_fs, 4, 1)

        diag_layout.addLayout(d_grid)

        btn_backup = QPushButton("Generate Complete Local Backup (.zip)")
        btn_backup.setProperty("class", "btn-success")
        btn_backup.setMinimumHeight(36)
        btn_backup.clicked.connect(self.create_full_backup)
        diag_layout.addWidget(btn_backup, alignment=Qt.AlignmentFlag.AlignLeft)

        layout.addWidget(diag_card)

        # 3. Software Licensing & 14-Day Evaluation Trial Card
        lic_card = QFrame()
        lic_card.setProperty("class", "card")
        lic_layout = QVBoxLayout(lic_card)
        lic_layout.setContentsMargins(18, 18, 18, 18)
        lic_layout.setSpacing(14)

        lic_title = QLabel("Software Licensing & 14-Day Evaluation Trial")
        lic_title.setStyleSheet("font-size: 15px; font-weight: 600; color: #0F172A;")
        lic_layout.addWidget(lic_title)

        l_grid = QGridLayout()
        l_grid.setHorizontalSpacing(16)
        l_grid.setVerticalSpacing(12)
        l_grid.setColumnMinimumWidth(0, 180)
        l_grid.setColumnStretch(1, 1)

        self.lbl_lic_status = QLabel()
        self.lbl_lic_dates = QLabel()
        self.lbl_lic_days = QLabel()

        lbl_s1 = QLabel("License Status:")
        lbl_s1.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        l_grid.addWidget(lbl_s1, 0, 0)
        l_grid.addWidget(self.lbl_lic_status, 0, 1)

        lbl_s2 = QLabel("Trial Evaluation Term:")
        lbl_s2.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        l_grid.addWidget(lbl_s2, 1, 0)
        l_grid.addWidget(self.lbl_lic_dates, 1, 1)

        lbl_s3 = QLabel("Days Remaining:")
        lbl_s3.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        l_grid.addWidget(lbl_s3, 2, 0)
        l_grid.addWidget(self.lbl_lic_days, 2, 1)

        lic_layout.addLayout(l_grid)

        # Activation row
        act_box = QHBoxLayout()
        act_box.setSpacing(10)

        self.lic_key_edit = QLineEdit()
        self.lic_key_edit.setPlaceholderText("Enter commercial license key to unlock lifetime access...")
        self.lic_key_edit.setMinimumHeight(36)
        self.lic_key_edit.returnPressed.connect(self.activate_license_key)

        btn_act = QPushButton("Activate License")
        btn_act.setProperty("class", "btn-primary")
        btn_act.setMinimumHeight(36)
        btn_act.clicked.connect(self.activate_license_key)

        act_box.addWidget(self.lic_key_edit, 1)
        act_box.addWidget(btn_act)
        lic_layout.addLayout(act_box)

        layout.addWidget(lic_card)

        # 3. User & Role Management Card (Admin Oversight)
        user_card = QFrame()
        user_card.setProperty("class", "card")
        user_layout = QVBoxLayout(user_card)
        user_layout.setContentsMargins(18, 18, 18, 18)
        user_layout.setSpacing(14)

        u_hdr = QHBoxLayout()
        u_title_box = QVBoxLayout()
        u_title = QLabel("Staff & User Accounts (Admin Authority & Password Control)")
        u_title.setStyleSheet("font-size: 15px; font-weight: 700; color: #0F172A;")
        u_sub = QLabel("Administrator creates staff accounts, designates authorities, and assigns passwords. Staff cannot self-change passwords.")
        u_sub.setStyleSheet("font-size: 12px; color: #64748B;")
        u_title_box.addWidget(u_title)
        u_title_box.addWidget(u_sub)
        u_hdr.addLayout(u_title_box)
        u_hdr.addStretch()

        btn_add_user = QPushButton("+ Add Staff / User Account")
        btn_add_user.setProperty("class", "btn-primary")
        btn_add_user.setStyleSheet("font-size: 12.5px; font-weight: 700; padding: 6px 16px;")
        btn_add_user.setMinimumHeight(36)
        btn_add_user.clicked.connect(self.open_create_user_dialog)
        u_hdr.addWidget(btn_add_user)
        user_layout.addLayout(u_hdr)

        self.users_table = QTableWidget()
        self.users_table.setColumnCount(6)
        self.users_table.setHorizontalHeaderLabels(["ID", "Full Name", "Username", "Authority / Role", "Status", "Password & Account Control"])
        self.users_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.users_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.users_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.users_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.users_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        self.users_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.users_table.setColumnWidth(2, 110)
        self.users_table.setColumnWidth(3, 110)
        self.users_table.setColumnWidth(4, 85)
        self.users_table.setMinimumHeight(240)
        configure_modern_table(self.users_table)
        user_layout.addWidget(self.users_table)

        layout.addWidget(user_card)
        layout.addStretch()

        scroll.setWidget(container)
        main_layout.addWidget(scroll)

    def refresh_data(self):
        conn = get_db_connection()
        try:
            row = conn.execute("SELECT * FROM organisation_profile LIMIT 1;").fetchone()
            if row:
                self.firm_name_edit.setText(row["firm_name"] or "")
                self.tagline_edit.setText(row["tagline"] or "")
                self.address_edit.setText(row["address"] or "")
                self.email_edit.setText(row["email"] or "")
                self.phone_edit.setText(row["phone"] or "")

            # Refresh users
            users = self.main_window.user_repo.list_all()
            self.users_table.setRowCount(0)
            for idx, u in enumerate(users):
                self.users_table.insertRow(idx)
                id_item = QTableWidgetItem(str(u.user_id))
                id_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.users_table.setItem(idx, 0, id_item)

                self.users_table.setItem(idx, 1, QTableWidgetItem(u.full_name))
                self.users_table.setItem(idx, 2, QTableWidgetItem(u.username))

                r_item = QTableWidgetItem(u.role.value)
                r_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.users_table.setItem(idx, 3, r_item)

                s_item = QTableWidgetItem("Active" if u.is_active else "Inactive")
                s_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.users_table.setItem(idx, 4, s_item)

                # Action buttons: Set Password & Remove
                act_widget = QWidget()
                act_layout = QHBoxLayout(act_widget)
                act_layout.setContentsMargins(6, 2, 6, 2)
                act_layout.setSpacing(6)

                btn_change_pw = QPushButton("🔑 Change PW")
                btn_change_pw.setProperty("class", "btn-secondary")
                btn_change_pw.setStyleSheet("font-size: 11px; font-weight: 600; padding: 3px 8px; color: #1D4ED8;")
                btn_change_pw.setToolTip(f"Assign a new password for {u.username}")
                btn_change_pw.clicked.connect(lambda _, user=u: self.open_reset_password_dialog(user))
                act_layout.addWidget(btn_change_pw)

                if u.username != "admin":
                    btn_del = QPushButton("🗑️ Remove")
                    btn_del.setProperty("class", "btn-secondary")
                    btn_del.setStyleSheet("font-size: 11px; font-weight: 600; padding: 3px 8px; color: #DC2626;")
                    btn_del.setToolTip(f"Delete or deactivate user {u.username}")
                    btn_del.clicked.connect(lambda _, user=u: self.delete_or_deactivate_user(user))
                    act_layout.addWidget(btn_del)

                self.users_table.setCellWidget(idx, 5, act_widget)

            # Refresh SMTP settings
            if hasattr(self.main_window, "email_service"):
                smtp_cfg = self.main_window.email_service.get_smtp_config()
                self.smtp_host_edit.setText(smtp_cfg.get("smtp_host", "smtp.gmail.com"))
                self.smtp_port_edit.setText(str(smtp_cfg.get("smtp_port", 587)))
                self.smtp_user_edit.setText(smtp_cfg.get("smtp_user", ""))
                self.smtp_tls_chk.setChecked(smtp_cfg.get("smtp_use_tls", True))
                if smtp_cfg.get("has_password"):
                    self.smtp_pass_edit.setPlaceholderText("•••••••••••••••• (App Password Saved Securely)")
                else:
                    self.smtp_pass_edit.setPlaceholderText("Enter 16-character App Password")

            # Refresh Licensing & Trial Display
            self.refresh_license_display()
        finally:
            conn.close()

    def refresh_license_display(self):
        """Update licensing status labels based on current database state."""
        from src.clientdesk_ai.security.licensing import LicenseService
        lic_service = LicenseService()
        info = lic_service.get_license_info()

        if info.is_activated:
            self.lbl_lic_status.setText("<b>✓ Full Lifetime License (Activated)</b>")
            self.lbl_lic_status.setStyleSheet("color: #059669; font-size: 13px;")
            self.lbl_lic_dates.setText(f"Initial Install: {info.start_date} • Full Access Unlocked")
            self.lbl_lic_days.setText("<b>Unlimited (Lifetime)</b>")
            self.lbl_lic_days.setStyleSheet("color: #059669; font-size: 13px;")
            self.lic_key_edit.setText(info.license_key)
            self.lic_key_edit.setEnabled(False)
        elif info.is_locked:
            self.lbl_lic_status.setText(f"<b>🔒 14-Day Trial Expired ({info.lock_reason})</b>")
            self.lbl_lic_status.setStyleSheet("color: #DC2626; font-size: 13px;")
            self.lbl_lic_dates.setText(f"Active from {info.start_date} to {info.expiry_date}")
            self.lbl_lic_days.setText("<b>0 Days (System Locked)</b>")
            self.lbl_lic_days.setStyleSheet("color: #DC2626; font-size: 13px;")
        else:
            self.lbl_lic_status.setText(f"<b>🕒 14-Day Evaluation Trial (Active)</b>")
            self.lbl_lic_status.setStyleSheet("color: #D97706; font-size: 13px;")
            self.lbl_lic_dates.setText(f"Start: {info.start_date}  •  Expiry: {info.expiry_date}")
            self.lbl_lic_days.setText(f"<b>{info.days_remaining} Day(s) Remaining</b>")
            self.lbl_lic_days.setStyleSheet("color: #2563EB; font-size: 13px;")

    def activate_license_key(self):
        """Handle license key activation from Settings view."""
        key = self.lic_key_edit.text().strip()
        from src.clientdesk_ai.security.licensing import LicenseService
        lic_service = LicenseService()
        ok, msg = lic_service.activate_license(key)
        if not ok:
            QMessageBox.warning(self, "Activation Failed", msg)
            return

        QMessageBox.information(
            self,
            "License Activated",
            "Commercial license successfully verified and activated.\n\n"
            "Full unlimited lifetime access is now enabled for Clientdesk AI."
        )
        self.refresh_license_display()
        if hasattr(self.main_window, "update_license_display"):
            self.main_window.update_license_display()

    def save_email_settings(self):
        host = self.smtp_host_edit.text().strip()
        port_text = self.smtp_port_edit.text().strip()
        user = self.smtp_user_edit.text().strip()
        password = self.smtp_pass_edit.text()
        use_tls = self.smtp_tls_chk.isChecked()

        if not host:
            QMessageBox.warning(self, "Validation Error", "Please provide a valid SMTP Host.")
            return

        try:
            port = int(port_text)
        except ValueError:
            QMessageBox.warning(self, "Validation Error", "SMTP Port must be a numeric integer (e.g. 587).")
            return

        if not user:
            QMessageBox.warning(self, "Validation Error", "Please provide a Sender Email Address.")
            return

        pass_to_save = password if password else None
        if hasattr(self.main_window, "email_service"):
            ok, msg = self.main_window.email_service.save_smtp_config(
                host=host, port=port, user=user, use_tls=use_tls, password=pass_to_save
            )
            if not ok:
                QMessageBox.warning(self, "Save Error", msg)
                return

        self.smtp_pass_edit.clear()
        self.smtp_pass_edit.setPlaceholderText("•••••••••••••••• (App Password Saved Securely)")
        QMessageBox.information(self, "Success", "Email & SMTP configuration saved successfully!")

    def open_create_user_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Add Staff / User Account (Admin Authority)")
        dialog.setMinimumWidth(440)
        d_layout = QVBoxLayout(dialog)
        d_layout.setContentsMargins(18, 18, 18, 18)
        d_layout.setSpacing(12)

        info_lbl = QLabel(
            "<b>Administrator User Management:</b><br>"
            "Specify the staff member's credentials and authority level. "
            "The password assigned here can only be modified by the Administrator; staff cannot change their own passwords."
        )
        info_lbl.setStyleSheet(
            "background-color: #EFF6FF; border: 1px solid #BFDBFE; "
            "border-radius: 6px; padding: 8px 10px; color: #1E40AF; font-size: 11.5px;"
        )
        info_lbl.setWordWrap(True)
        d_layout.addWidget(info_lbl)

        grid = QGridLayout()
        grid.setSpacing(8)
        u_name = QLineEdit()
        u_name.setPlaceholderText("e.g. rahul, sneha, operator1")
        f_name = QLineEdit()
        f_name.setPlaceholderText("e.g. Rahul Mehta")
        email = QLineEdit()
        email.setPlaceholderText("e.g. rahul@firm.com (Optional)")
        pwd = QLineEdit()
        pwd.setEchoMode(QLineEdit.EchoMode.Password)
        pwd.setPlaceholderText("Enter password assigned by Admin")

        role_combo = QComboBox()
        role_combo.addItem("STAFF — Operator / Preparer (Default)", "STAFF")
        role_combo.addItem("SENIOR — Senior Reviewer", "SENIOR")
        role_combo.addItem("PARTNER — Partner / Practice Head", "PARTNER")
        role_combo.addItem("ADMIN — Full System Administrator", "ADMIN")
        role_combo.addItem("READ_ONLY — External Auditor / Observer", "READ_ONLY")

        grid.addWidget(QLabel("Username *:"), 0, 0)
        grid.addWidget(u_name, 0, 1)
        grid.addWidget(QLabel("Full Name *:"), 1, 0)
        grid.addWidget(f_name, 1, 1)
        grid.addWidget(QLabel("Email:"), 2, 0)
        grid.addWidget(email, 2, 1)
        grid.addWidget(QLabel("Assigned Password *:"), 3, 0)
        grid.addWidget(pwd, 3, 1)
        grid.addWidget(QLabel("Authority / Role *:"), 4, 0)
        grid.addWidget(role_combo, 4, 1)
        d_layout.addLayout(grid)

        btn_box = QHBoxLayout()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setProperty("class", "btn-secondary")
        btn_cancel.clicked.connect(dialog.reject)

        btn_create = QPushButton("Create Account & Set Password")
        btn_create.setProperty("class", "btn-primary")
        btn_create.setStyleSheet("font-weight: 700;")

        def save_user():
            raw_username = u_name.text().strip().lower()
            raw_pwd = pwd.text().strip()
            raw_fname = f_name.text().strip() or raw_username.capitalize()
            raw_email = email.text().strip() or f"{raw_username}@clientdesk.local"

            if not raw_username or not raw_pwd:
                QMessageBox.warning(dialog, "Required Fields", "Username and Password are required.")
                return

            existing = self.main_window.user_repo.get_by_username(raw_username)
            if existing:
                QMessageBox.warning(dialog, "User Exists", f"A user with username '{raw_username}' already exists.")
                return

            chosen_role_str = role_combo.currentData()
            new_u = User(
                username=raw_username,
                full_name=raw_fname,
                email=raw_email,
                password_hash=hash_password(raw_pwd),
                role=UserRole(chosen_role_str)
            )
            try:
                self.main_window.user_repo.create_user(new_u)
                QMessageBox.information(
                    dialog, "Account Created",
                    f"Staff account '{new_u.username}' ({new_u.full_name}) created successfully.\n\n"
                    f"Authority: {new_u.role.value}\n"
                    f"Assigned Password: {raw_pwd}\n\n"
                    "Provide these credentials to the staff member. Staff cannot change their password."
                )
                dialog.accept()
                self.refresh_data()
            except Exception as ex:
                QMessageBox.critical(dialog, "Error", f"Failed to create user: {str(ex)}")

        btn_create.clicked.connect(save_user)
        btn_box.addStretch()
        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(btn_create)
        d_layout.addLayout(btn_box)

        dialog.exec()

    def open_reset_password_dialog(self, user: User):
        """Allow Administrator to set or change the password for any staff account."""
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Set Password for {user.username}")
        dialog.setMinimumWidth(380)
        d_layout = QVBoxLayout(dialog)
        d_layout.setContentsMargins(16, 16, 16, 16)
        d_layout.setSpacing(12)

        prompt_lbl = QLabel(f"<b>Assign New Password for {user.full_name} ({user.username}):</b>")
        prompt_lbl.setStyleSheet("font-size: 13px; color: #0F172A;")
        d_layout.addWidget(prompt_lbl)

        note_lbl = QLabel(
            "Note: Staff members cannot change their own password. "
            "The new password you set below will immediately be required for their login."
        )
        note_lbl.setStyleSheet("font-size: 11px; color: #64748B;")
        note_lbl.setWordWrap(True)
        d_layout.addWidget(note_lbl)

        new_pwd_edit = QLineEdit()
        new_pwd_edit.setPlaceholderText("Enter new password")
        new_pwd_edit.setEchoMode(QLineEdit.EchoMode.Password)
        new_pwd_edit.setFixedHeight(34)
        d_layout.addWidget(new_pwd_edit)

        chk_show = QCheckBox("Show Password")
        chk_show.toggled.connect(
            lambda checked: new_pwd_edit.setEchoMode(QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password)
        )
        d_layout.addWidget(chk_show)

        btn_box = QHBoxLayout()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setProperty("class", "btn-secondary")
        btn_cancel.clicked.connect(dialog.reject)

        btn_save = QPushButton("Update Password")
        btn_save.setProperty("class", "btn-primary")

        def perform_update():
            p_text = new_pwd_edit.text().strip()
            if not p_text:
                QMessageBox.warning(dialog, "Password Required", "Please enter a valid non-empty password.")
                return

            new_hash = hash_password(p_text)
            ok = self.main_window.user_repo.update_password(user.user_id, new_hash)
            if ok:
                QMessageBox.information(
                    dialog, "Password Updated",
                    f"Password for '{user.username}' successfully updated to: '{p_text}'.\n\n"
                    "Please provide this new password to the staff member."
                )
                dialog.accept()
                self.refresh_data()
            else:
                QMessageBox.critical(dialog, "Error", "Failed to update password in database.")

        btn_save.clicked.connect(perform_update)
        btn_box.addStretch()
        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(btn_save)
        d_layout.addLayout(btn_box)

        dialog.exec()

    def delete_or_deactivate_user(self, user: User):
        """Allow Administrator to remove or deactivate a staff member."""
        if user.username == "admin":
            QMessageBox.warning(self, "Action Prohibited", "The primary Administrator ('admin') account cannot be deleted.")
            return

        confirm = QMessageBox.question(
            self,
            "Confirm User Removal",
            f"Are you sure you want to remove staff member '{user.username}' ({user.full_name})?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        ok, msg = self.main_window.user_repo.delete_user(user.user_id)
        if ok:
            QMessageBox.information(self, "User Account Updated", msg)
            self.refresh_data()
        else:
            QMessageBox.critical(self, "Error", msg)

    def save_org_profile(self):
        now = datetime.now(timezone.utc).isoformat()
        conn = get_db_connection()
        try:
            with conn:
                conn.execute(
                    """
                    UPDATE organisation_profile
                    SET firm_name = ?, tagline = ?, address = ?, email = ?, phone = ?, updated_at = ?
                    WHERE org_id = 1;
                    """,
                    (self.firm_name_edit.text().strip(), self.tagline_edit.text().strip(),
                     self.address_edit.text().strip(), self.email_edit.text().strip(),
                     self.phone_edit.text().strip(), now)
                )
            QMessageBox.information(self, "Saved", "Organization profile settings saved successfully.")
            if hasattr(self.main_window, "update_firm_display"):
                self.main_window.update_firm_display()
        finally:
            conn.close()

    def create_full_backup(self):
        now_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_zip_path = CONFIG.backup_path / f"clientdesk_backup_{now_str}.zip"

        try:
            with zipfile.ZipFile(str(backup_zip_path), "w", zipfile.ZIP_DEFLATED) as zipf:
                # 1. Vacuum / Safe backup SQLite database
                temp_db = CONFIG.backup_path / f"temp_{now_str}.db"
                conn = get_db_connection()
                try:
                    conn.execute(f"VACUUM INTO '{str(temp_db).replace(chr(92), '/')}'")
                finally:
                    conn.close()

                zipf.write(str(temp_db), arcname="database/clientdesk.db")
                if temp_db.exists():
                    temp_db.unlink()

                # 2. Add Filestore files
                if CONFIG.filestore_path.exists():
                    for f in CONFIG.filestore_path.rglob("*"):
                        if f.is_file():
                            arc_rel = f"filestore/{f.relative_to(CONFIG.filestore_path)}"
                            zipf.write(str(f), arcname=arc_rel)

            size_mb = round(backup_zip_path.stat().st_size / (1024 * 1024), 2)
            QMessageBox.information(
                self, "Backup Generated",
                f"Full offline archive successfully created!\n\nLocation: {backup_zip_path}\nArchive Size: {size_mb} MB"
            )
        except Exception as e:
            QMessageBox.critical(self, "Backup Failed", f"An error occurred while creating backup:\n{str(e)}")
