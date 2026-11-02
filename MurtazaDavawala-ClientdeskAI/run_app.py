"""Clientdesk AI - Desktop Application Entry Point."""

import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.clientdesk_ai.config.settings import CONFIG
from src.clientdesk_ai.persistence.database import init_database
from src.clientdesk_ai.persistence.seed_data import seed_database
from src.clientdesk_ai.ui.qt_compat import QApplication, QDialog, Qt
from src.clientdesk_ai.ui.main_window import MainWindow
from src.clientdesk_ai.ui.views.login_dialog import LoginDialog
from src.clientdesk_ai.security.licensing import LicenseService
from src.clientdesk_ai.ui.views.license_dialog import LicenseActivationDialog


def main():
    # 1. Initialize SQLite Database & Seed Data
    init_database()
    seed_database()

    # 2. Configure High DPI Scaling Policy (Must be set BEFORE instantiating QApplication)
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    # 3. Launch Qt Application
    app = QApplication(sys.argv)
    app.setApplicationName(CONFIG.app_name)
    app.setApplicationVersion(CONFIG.version)

    # 4. 14-Day Evaluation Trial & Licensing Lock Enforcement
    license_service = LicenseService()
    lic_info = license_service.get_license_info()
    if lic_info.is_locked:
        lock_dialog = LicenseActivationDialog(license_service=license_service, is_blocking_lock=True)
        if lock_dialog.exec() != QDialog.DialogCode.Accepted:
            sys.exit(0)

    # 4. Require ID & Password on Application Startup
    login_dialog = LoginDialog()
    if login_dialog.exec() == QDialog.DialogCode.Accepted and login_dialog.authenticated_user:
        window = MainWindow(current_user=login_dialog.authenticated_user)
        window.show()
        sys.exit(app.exec())
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
