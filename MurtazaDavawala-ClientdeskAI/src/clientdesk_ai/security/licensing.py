"""14-Day Evaluation Trial and Software Licensing Management System.

Features:
- Enforces strict 14-day trial period from date of initial installation.
- Automatically locks the application once the 14-day trial period concludes.
- Clock rollback / tampering detection preventing system time manipulation.
- Commercial license key activation mechanism to unlock lifetime access.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import re
from typing import Optional, Tuple
from src.clientdesk_ai.config.settings import CONFIG
from src.clientdesk_ai.persistence.database import get_db_connection

TRIAL_DAYS = 14

VALID_MASTER_KEYS = {
    "CDAI-2026-PRO-LIFETIME",
    "XYZ-CO-PRO-2026-KEY",
    "CLIENTDESK-PRO-14D-UNLOCKED",
    "MURTAZA-DAVAWALA-PRO-2026",
    "CDAI-FULL-LICENSE-2026",
}


@dataclass
class LicenseInfo:
    status: str            # 'TRIAL' or 'ACTIVATED'
    start_date: str        # ISO date 'YYYY-MM-DD'
    expiry_date: str       # ISO date 'YYYY-MM-DD'
    last_run_date: str     # ISO date 'YYYY-MM-DD'
    license_key: str       # Key used to activate or ''
    days_remaining: int    # 0 to 14
    is_activated: bool     # True if unlocked with commercial license
    is_expired: bool       # True if trial expired
    is_tampered: bool      # True if clock rollback detected
    is_locked: bool        # True if system access should be blocked
    lock_reason: str       # Human-readable explanation if locked


class LicenseService:
    """Manages trial countdown, clock verification, and software activation."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or CONFIG.db_path

    def _get_setting(self, conn, key: str, default: str = "") -> str:
        row = conn.execute(
            "SELECT setting_value FROM app_settings WHERE setting_key = ?;", (key,)
        ).fetchone()
        return row["setting_value"] if row else default

    def _set_setting(self, conn, key: str, val: str) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            INSERT INTO app_settings (setting_key, setting_value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(setting_key) DO UPDATE SET
                setting_value = excluded.setting_value,
                updated_at = excluded.updated_at;
            """,
            (key, val, now_iso)
        )

    def initialize_trial_if_needed(self) -> None:
        """Initialize trial settings on first installation if not already set."""
        conn = get_db_connection(self.db_path)
        try:
            with conn:
                existing = self._get_setting(conn, "trial_start_date")
                if not existing:
                    today = date.today().isoformat()
                    expiry = (date.today() + timedelta(days=TRIAL_DAYS)).isoformat()
                    self._set_setting(conn, "trial_start_date", today)
                    self._set_setting(conn, "trial_expiry_date", expiry)
                    self._set_setting(conn, "license_status", "TRIAL")
                    self._set_setting(conn, "license_key", "")
                    self._set_setting(conn, "license_last_run_date", today)
        finally:
            conn.close()

    def get_license_info(self) -> LicenseInfo:
        """Inspect current trial, clock integrity, and license status."""
        self.initialize_trial_if_needed()
        conn = get_db_connection(self.db_path)
        try:
            status = self._get_setting(conn, "license_status", "TRIAL").upper()
            start_str = self._get_setting(conn, "trial_start_date", date.today().isoformat())
            expiry_str = self._get_setting(conn, "trial_expiry_date")
            last_run_str = self._get_setting(conn, "license_last_run_date", date.today().isoformat())
            key = self._get_setting(conn, "license_key", "")

            # If expiry not set, default to 14 days from start
            if not expiry_str:
                try:
                    st_date = date.fromisoformat(start_str[:10])
                except Exception:
                    st_date = date.today()
                expiry_str = (st_date + timedelta(days=TRIAL_DAYS)).isoformat()
                with conn:
                    self._set_setting(conn, "trial_expiry_date", expiry_str)

            today = date.today()
            today_str = today.isoformat()

            try:
                exp_date = date.fromisoformat(expiry_str[:10])
            except Exception:
                exp_date = today + timedelta(days=TRIAL_DAYS)

            try:
                last_run_date = date.fromisoformat(last_run_str[:10])
            except Exception:
                last_run_date = today

            # 1. Check for clock rollback tampering
            is_tampered = False
            if today < last_run_date:
                is_tampered = True

            # Update last run date if advancing normally
            if not is_tampered and today > last_run_date:
                with conn:
                    self._set_setting(conn, "license_last_run_date", today_str)

            is_activated = (status == "ACTIVATED")
            days_left = max(0, (exp_date - today).days)
            is_expired = (not is_activated) and (today > exp_date)

            is_locked = False
            lock_reason = ""

            if not is_activated:
                if is_tampered:
                    is_locked = True
                    lock_reason = (
                        "System clock manipulation detected. The system has been locked for security. "
                        "Please restore your clock or activate a license key to proceed."
                    )
                elif is_expired:
                    is_locked = True
                    lock_reason = (
                        f"Your 14-day evaluation trial concluded on {exp_date}. "
                        "The system is currently locked. Please activate a commercial license key to continue."
                    )

            return LicenseInfo(
                status=status,
                start_date=start_str[:10],
                expiry_date=expiry_str[:10],
                last_run_date=last_run_str[:10],
                license_key=key,
                days_remaining=0 if is_expired else days_left,
                is_activated=is_activated,
                is_expired=is_expired,
                is_tampered=is_tampered,
                is_locked=is_locked,
                lock_reason=lock_reason
            )
        finally:
            conn.close()

    def validate_key(self, raw_key: str) -> bool:
        """Verify whether a license key matches known master keys or algorithmic format."""
        if not raw_key:
            return False
        clean = raw_key.strip().upper()
        if clean in VALID_MASTER_KEYS:
            return True

        # Algorithmic pattern: CDAI-XXXX-XXXX-XXXX where checksum passes
        # Example: CDAI-7B2F-9C14-A3D8
        pattern = r"^CDAI-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$"
        if re.match(pattern, clean):
            # Checksum rule: sum of ASCII character values % 13 == 0
            payload = clean.replace("-", "")
            return (sum(ord(c) for c in payload) % 13) == 0

        return False

    def activate_license(self, raw_key: str) -> Tuple[bool, str]:
        """Activate the software using a commercial license key, removing trial limits."""
        if not raw_key or not raw_key.strip():
            return False, "Please enter an activation license key."

        clean = raw_key.strip().upper()
        if not self.validate_key(clean):
            return False, "Invalid license key. Please verify your activation code and try again."

        conn = get_db_connection(self.db_path)
        try:
            with conn:
                self._set_setting(conn, "license_status", "ACTIVATED")
                self._set_setting(conn, "license_key", clean)
                self._set_setting(conn, "license_activated_at", datetime.now(timezone.utc).isoformat())
            return True, "License successfully activated! Full lifetime access is now unlocked."
        finally:
            conn.close()

    def set_trial_dates_for_testing(self, start_date: date, expiry_date: date, status: str = "TRIAL") -> None:
        """Utility for test suites to simulate trial expiration or active state."""
        conn = get_db_connection(self.db_path)
        try:
            with conn:
                self._set_setting(conn, "trial_start_date", start_date.isoformat())
                self._set_setting(conn, "trial_expiry_date", expiry_date.isoformat())
                self._set_setting(conn, "license_last_run_date", start_date.isoformat())
                self._set_setting(conn, "license_status", status)
                if status != "ACTIVATED":
                    self._set_setting(conn, "license_key", "")
        finally:
            conn.close()
