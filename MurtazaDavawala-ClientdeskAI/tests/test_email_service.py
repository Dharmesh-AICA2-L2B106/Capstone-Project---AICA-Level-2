"""Unit tests for EmailService, keyring secure storage, and PDF attachment generation."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
import smtplib

from src.clientdesk_ai.application.services import EmailService
from src.clientdesk_ai.persistence.database import init_database
from src.clientdesk_ai.persistence.seed_data import seed_database
from src.clientdesk_ai.domain.models import Client, EngagementChecklistItem, RequirementType, DocumentStatus, ApplicabilityStatus


class TestEmailService(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_clientdesk.db"
        init_database(self.db_path)
        seed_database(self.db_path)
        self.email_service = EmailService(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_default_smtp_config(self):
        """Verify default SMTP settings seeded in SQLite."""
        cfg = self.email_service.get_smtp_config()
        self.assertEqual(cfg["smtp_host"], "smtp.gmail.com")
        self.assertEqual(cfg["smtp_port"], 587)
        self.assertEqual(cfg["smtp_user"], "")
        self.assertTrue(cfg["smtp_use_tls"])

    def test_save_and_retrieve_smtp_config(self):
        """Verify saving SMTP settings to DB and password to keyring."""
        with patch("keyring.set_password") as mock_set, patch("keyring.get_password") as mock_get:
            mock_get.return_value = "app_pass_xyz123"

            ok, msg = self.email_service.save_smtp_config(
                host="smtp.office365.com",
                port=587,
                user="accounts@myfirm.com",
                use_tls=True,
                password="app_pass_xyz123"
            )
            self.assertTrue(ok)
            mock_set.assert_called_with("clientdesk", "smtp_pass", "app_pass_xyz123")

            cfg = self.email_service.get_smtp_config()
            self.assertEqual(cfg["smtp_host"], "smtp.office365.com")
            self.assertEqual(cfg["smtp_user"], "accounts@myfirm.com")
            self.assertTrue(cfg["has_password"])

    def test_validation_checks(self):
        """Verify validation errors for unconfigured settings, missing email, or missing password."""
        # Unconfigured sender
        ok, msg = self.email_service.send_checklist_email("client@test.com", "Subj", "Body")
        self.assertFalse(ok)
        self.assertIn("not configured", msg.lower())

        # Configured sender, but missing recipient
        self.email_service.save_smtp_config("smtp.gmail.com", 587, "firm@gmail.com")
        ok, msg = self.email_service.send_checklist_email("", "Subj", "Body")
        self.assertFalse(ok)
        self.assertIn("invalid recipient", msg.lower())

        # Configured sender, but no password in keyring
        with patch("keyring.get_password", return_value=None):
            ok, msg = self.email_service.send_checklist_email("client@test.com", "Subj", "Body")
            self.assertFalse(ok)
            self.assertIn("password is not set", msg.lower())

    @patch("smtplib.SMTP")
    @patch("keyring.get_password", return_value="secret_app_pw")
    def test_successful_smtp_dispatch_with_pdf(self, mock_pw, mock_smtp_cls):
        """Verify successful message construction, starttls, login, and send_message with PDF."""
        self.email_service.save_smtp_config("smtp.gmail.com", 587, "firm@gmail.com")

        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_server

        # Create dummy PDF file
        pdf_file = Path(self.temp_dir.name) / "checklist.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 dummy pdf data")

        ok, msg = self.email_service.send_checklist_email(
            to_email="client@example.com",
            subject="Tax Document Checklist",
            body_text="Dear Client,\nPlease find attached your required documents.",
            pdf_path=str(pdf_file)
        )

        self.assertTrue(ok)
        self.assertEqual(msg, "Email sent successfully.")

        # Verify server calls
        mock_smtp_cls.assert_called_with("smtp.gmail.com", 587, timeout=20)
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_with("firm@gmail.com", "secret_app_pw")
        mock_server.send_message.assert_called_once()

        # Verify attached message
        sent_msg = mock_server.send_message.call_args[0][0]
        self.assertEqual(sent_msg["Subject"], "Tax Document Checklist")
        self.assertEqual(sent_msg["From"], "firm@gmail.com")
        self.assertEqual(sent_msg["To"], "client@example.com")

    @patch("smtplib.SMTP")
    @patch("keyring.get_password", return_value="secret_app_pw")
    def test_smtp_auth_error_handling(self, mock_pw, mock_smtp_cls):
        """Verify SMTPAuthenticationError is caught cleanly without crash."""
        self.email_service.save_smtp_config("smtp.gmail.com", 587, "firm@gmail.com")

        mock_server = MagicMock()
        mock_server.login.side_effect = smtplib.SMTPAuthenticationError(535, b"5.7.8 Username and Password not accepted")
        mock_smtp_cls.return_value.__enter__.return_value = mock_server

        ok, msg = self.email_service.send_checklist_email(
            to_email="client@example.com",
            subject="Tax Checklist",
            body_text="Body"
        )
        self.assertFalse(ok)
        self.assertIn("Authentication Error", msg)


if __name__ == "__main__":
    unittest.main()
