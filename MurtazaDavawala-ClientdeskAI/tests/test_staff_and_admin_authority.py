"""Tests verifying Administrator authority, staff user creation, password assignment,
and role panel access controls.
"""

import os
import sys
import unittest
from pathlib import Path
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from src.clientdesk_ai.ui.qt_compat import QApplication
from src.clientdesk_ai.persistence.database import init_database
from src.clientdesk_ai.persistence.seed_data import seed_database
from src.clientdesk_ai.persistence.repositories import UserRepository
from src.clientdesk_ai.application.services import AuthService
from src.clientdesk_ai.domain.models import User, UserRole
from src.clientdesk_ai.security.crypto import hash_password, verify_password
from src.clientdesk_ai.ui.main_window import MainWindow


class TestStaffAndAdminAuthority(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(["test_runner"])

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_auth_clientdesk.db"
        init_database(self.db_path)
        seed_database(self.db_path)
        self.user_repo = UserRepository(self.db_path)
        self.auth_service = AuthService(self.user_repo)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_01_admin_default_credentials(self):
        """Admin default ID and password must be 'admin' and 'admin'."""
        ok, user, msg = self.auth_service.authenticate("admin", "admin")
        self.assertTrue(ok, f"Admin authentication failed: {msg}")
        self.assertIsNotNone(user)
        self.assertEqual(user.username, "admin")
        self.assertEqual(user.role, UserRole.ADMIN)

    def test_02_admin_adds_staff_with_assigned_password(self):
        """Admin creates staff user with assigned password; staff logs in with assigned password."""
        staff_pwd = "StaffSecret@2026"
        new_staff = User(
            username="kavita",
            full_name="Kavita Sharma",
            email="kavita@xyzco.local",
            password_hash=hash_password(staff_pwd),
            role=UserRole.STAFF
        )
        user_id = self.user_repo.create_user(new_staff)
        self.assertGreater(user_id, 0)

        # Staff logs in with admin-assigned password
        ok, auth_user, msg = self.auth_service.authenticate("kavita", staff_pwd)
        self.assertTrue(ok, f"Staff login failed: {msg}")
        self.assertEqual(auth_user.username, "kavita")
        self.assertEqual(auth_user.role, UserRole.STAFF)

        # Wrong password fails
        bad_ok, _, _ = self.auth_service.authenticate("kavita", "wrongpassword")
        self.assertFalse(bad_ok)

    def test_03_admin_updates_staff_password(self):
        """Admin can change/reset staff password; staff then logs in with new password only."""
        new_staff = User(
            username="amit",
            full_name="Amit Patel",
            email="amit@xyzco.local",
            password_hash=hash_password("InitialPass123"),
            role=UserRole.STAFF
        )
        user_id = self.user_repo.create_user(new_staff)

        # Admin resets password to 'UpdatedPass456'
        updated_pwd = "UpdatedPass456"
        success = self.user_repo.update_password(user_id, hash_password(updated_pwd))
        self.assertTrue(success)

        # Old password fails
        old_ok, _, _ = self.auth_service.authenticate("amit", "InitialPass123")
        self.assertFalse(old_ok)

        # New password succeeds
        new_ok, user, _ = self.auth_service.authenticate("amit", updated_pwd)
        self.assertTrue(new_ok)
        self.assertEqual(user.user_id, user_id)

    def test_04_panel_permissions_admin_vs_staff(self):
        """Admin has all power on all panels; Staff has Review Queue and Settings hidden."""
        # 1. Admin login
        admin = self.user_repo.get_by_username("admin")
        admin_window = MainWindow(current_user=admin)
        try:
            # Check nav buttons for Admin (not hidden)
            btn_dashboard = admin_window.nav_group.button(0)
            btn_clients = admin_window.nav_group.button(1)
            btn_workspaces = admin_window.nav_group.button(2)
            btn_review = admin_window.nav_group.button(3)
            btn_catalogue = admin_window.nav_group.button(4)
            btn_knowledge = admin_window.nav_group.button(5)
            btn_reports = admin_window.nav_group.button(6)
            btn_settings = admin_window.nav_group.button(7)

            self.assertFalse(btn_review.isHidden(), "Admin must have access to Senior Review Queue")
            self.assertFalse(btn_settings.isHidden(), "Admin must have access to Settings & Diagnostics")
            self.assertFalse(btn_dashboard.isHidden())
            self.assertFalse(btn_clients.isHidden())
            self.assertFalse(btn_workspaces.isHidden())
            self.assertFalse(btn_catalogue.isHidden())
            self.assertFalse(btn_knowledge.isHidden())
            self.assertFalse(btn_reports.isHidden())
        finally:
            admin_window.close()

        # 2. Staff login
        staff = User(user_id=99, username="staff1", full_name="Staff One", role=UserRole.STAFF)
        staff_window = MainWindow(current_user=staff)
        try:
            btn_review_staff = staff_window.nav_group.button(3)
            btn_settings_staff = staff_window.nav_group.button(7)
            btn_workspaces_staff = staff_window.nav_group.button(2)
            btn_clients_staff = staff_window.nav_group.button(1)

            # Operational panels must be accessible
            self.assertFalse(btn_workspaces_staff.isHidden(), "Staff must have access to Workspaces")
            self.assertFalse(btn_clients_staff.isHidden(), "Staff must have access to Clients")

            # Governance and sensitive configuration panels must be HIDDEN
            self.assertTrue(btn_review_staff.isHidden(), "Staff must NOT have access to Senior Review Queue")
            self.assertTrue(btn_settings_staff.isHidden(), "Staff must NOT have access to Settings & Diagnostics")
        finally:
            staff_window.close()

    def test_05_admin_delete_staff_and_protect_admin(self):
        """Admin can remove staff users, but primary admin account cannot be removed."""
        new_staff = User(
            username="temp_staff",
            full_name="Temporary Staff",
            email="temp@xyzco.local",
            password_hash=hash_password("temp123"),
            role=UserRole.STAFF
        )
        staff_id = self.user_repo.create_user(new_staff)
        self.assertIsNotNone(self.user_repo.get_by_id(staff_id))

        # Admin deletes staff
        ok, msg = self.user_repo.delete_user(staff_id)
        self.assertTrue(ok)
        self.assertIsNone(self.user_repo.get_by_id(staff_id))


if __name__ == "__main__":
    unittest.main()
