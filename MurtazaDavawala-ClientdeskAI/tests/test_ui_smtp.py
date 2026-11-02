import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import sys
import unittest
from pathlib import Path

from src.clientdesk_ai.ui.qt_compat import QApplication
from src.clientdesk_ai.persistence.database import init_database
from src.clientdesk_ai.persistence.seed_data import seed_database
from src.clientdesk_ai.ui.main_window import MainWindow
from src.clientdesk_ai.ui.views.send_requirements_dialog import SendRequirementsDialog

class TestUIIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)
        init_database()
        seed_database()
        cls.win = MainWindow()

    def test_settings_view_smtp_card(self):
        settings_view = self.win.settings_view
        settings_view.refresh_data()
        self.assertIsNotNone(settings_view.smtp_host_edit)
        self.assertEqual(settings_view.smtp_host_edit.text(), "smtp.gmail.com")
        self.assertEqual(settings_view.smtp_port_edit.text(), "587")

    def test_send_requirements_dialog_ui(self):
        dialog = SendRequirementsDialog(self.win, engagement_id=1)
        self.assertIsNotNone(dialog.btn_send_email)
        self.assertEqual(dialog.btn_send_email.text(), "📧 Send via Email Now")
        self.assertEqual(dialog.btn_send_email.minimumHeight(), 36)

        # Test PDF generation method
        client = self.win.client_repo.get_by_id(1)
        items_by_eng = dialog.get_selected_items_by_engagement()
        if client and items_by_eng:
            pdf_path = dialog.generate_checklist_pdf(client, items_by_eng)
            self.assertTrue(Path(pdf_path).exists())
            self.assertTrue(Path(pdf_path).stat().st_size > 100)
            print("Generated test checklist PDF size:", Path(pdf_path).stat().st_size)


if __name__ == "__main__":
    unittest.main()
