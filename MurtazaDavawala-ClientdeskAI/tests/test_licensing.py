"""Unit tests validating 14-day evaluation trial, lock enforcement, and licensing activation."""

from datetime import date, timedelta
from pathlib import Path
import tempfile
import unittest

from src.clientdesk_ai.persistence.database import init_database
from src.clientdesk_ai.security.licensing import LicenseService, VALID_MASTER_KEYS


class TestLicensingAndTrial(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_license.db"
        init_database(self.db_path)
        self.service = LicenseService(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_01_initial_trial_duration_is_14_days(self):
        """Verify that on initial setup the trial period is exactly 14 calendar days."""
        info = self.service.get_license_info()
        self.assertEqual(info.status, "TRIAL")
        self.assertFalse(info.is_activated)
        self.assertFalse(info.is_expired)
        self.assertFalse(info.is_locked)
        self.assertEqual(info.days_remaining, 14)
        self.assertEqual(info.start_date, date.today().isoformat())
        self.assertEqual(info.expiry_date, (date.today() + timedelta(days=14)).isoformat())

    def test_02_trial_active_during_14_days(self):
        """Verify that when 5 days have elapsed, 9 days remain and system remains unlocked."""
        start = date.today() - timedelta(days=5)
        expiry = start + timedelta(days=14)
        self.service.set_trial_dates_for_testing(start, expiry)

        info = self.service.get_license_info()
        self.assertEqual(info.days_remaining, 9)
        self.assertFalse(info.is_expired)
        self.assertFalse(info.is_locked)

    def test_03_trial_expires_and_locks_after_14_days(self):
        """Verify that once 14 days pass, the system locks and blocks access."""
        start = date.today() - timedelta(days=15)
        expiry = date.today() - timedelta(days=1)
        self.service.set_trial_dates_for_testing(start, expiry)

        info = self.service.get_license_info()
        self.assertTrue(info.is_expired)
        self.assertTrue(info.is_locked)
        self.assertEqual(info.days_remaining, 0)
        self.assertIn("concluded", info.lock_reason.lower())

    def test_04_clock_rollback_tampering_detected_and_locked(self):
        """Verify that turning back system clock triggers security lock."""
        # Simulate app last run yesterday, but current clock set to 5 days ago
        self.service.initialize_trial_if_needed()
        future_run = date.today() + timedelta(days=2)
        # Directly set last run date to future to simulate user setting clock back
        conn = self.service.db_path
        from src.clientdesk_ai.persistence.database import get_db_connection
        db = get_db_connection(conn)
        with db:
            db.execute(
                "UPDATE app_settings SET setting_value = ? WHERE setting_key = 'license_last_run_date';",
                (future_run.isoformat(),)
            )
        db.close()

        info = self.service.get_license_info()
        self.assertTrue(info.is_tampered)
        self.assertTrue(info.is_locked)
        self.assertIn("clock manipulation", info.lock_reason.lower())

    def test_05_invalid_license_key_rejected(self):
        """Verify invalid or bogus license keys are rejected with error."""
        ok, msg = self.service.activate_license("INVALID-KEY-123")
        self.assertFalse(ok)
        self.assertIn("Invalid license key", msg)

        ok2, msg2 = self.service.activate_license("")
        self.assertFalse(ok2)

    def test_06_valid_master_key_unlocks_locked_system(self):
        """Verify that activating with master commercial key unlocks an expired trial."""
        # First expire the trial
        start = date.today() - timedelta(days=20)
        expiry = date.today() - timedelta(days=6)
        self.service.set_trial_dates_for_testing(start, expiry)
        self.assertTrue(self.service.get_license_info().is_locked)

        # Activate with known commercial key
        ok, msg = self.service.activate_license("CDAI-2026-PRO-LIFETIME")
        self.assertTrue(ok)
        self.assertIn("successfully activated", msg)

        # Verify system is unlocked and status is ACTIVATED
        info = self.service.get_license_info()
        self.assertTrue(info.is_activated)
        self.assertFalse(info.is_locked)
        self.assertFalse(info.is_expired)
        self.assertEqual(info.status, "ACTIVATED")
        self.assertEqual(info.license_key, "CDAI-2026-PRO-LIFETIME")


if __name__ == "__main__":
    unittest.main()
