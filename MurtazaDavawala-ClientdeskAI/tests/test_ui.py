"""Automated headless UI tests validating window initialization and view transitions."""

import os
import sys
import unittest
from pathlib import Path
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from src.clientdesk_ai.ui.qt_compat import QApplication
from src.clientdesk_ai.ui.main_window import MainWindow
from src.clientdesk_ai.persistence.database import init_database
from src.clientdesk_ai.persistence.seed_data import seed_database
from src.clientdesk_ai.domain.models import User, UserRole


class TestMainWindowUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(["test_runner"])
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.db_path = Path(cls.temp_dir.name) / "test_clientdesk.db"
        init_database(cls.db_path)
        seed_database(cls.db_path)
        admin = User(user_id=1, username="admin", full_name="Admin User", role=UserRole.ADMIN)
        cls.window = MainWindow(current_user=admin)

    @classmethod
    def tearDownClass(cls):
        cls.window.close()
        cls.temp_dir.cleanup()

    def test_window_views_switching(self):
        # Test switching across all 8 views without exception
        for tab_idx in range(8):
            self.window.switch_tab(tab_idx)
            self.assertEqual(self.window.stacked_widget.currentIndex(), tab_idx)

    def test_dashboard_and_catalog_populates(self):
        self.window.switch_tab(0)
        self.assertGreaterEqual(self.window.dashboard_view.table.rowCount(), 0)

        # Service Catalog must have at least 8 baseline source definitions under the approved groups
        self.window.switch_tab(4)
        self.assertGreaterEqual(self.window.templates_view.service_table.rowCount(), 8)

    def test_knowledge_search_view(self):
        self.window.switch_tab(5)
        self.window.knowledge_view.search_edit.setText("GST")
        self.window.knowledge_view.perform_search()
        self.assertGreater(self.window.knowledge_view.results_table.rowCount(), 0)

    def test_high_dpi_sidebar_and_action_bar_layout(self):
        from src.clientdesk_ai.ui.qt_compat import QHeaderView
        # 1. Minimum window size is at least 1280x800
        min_size = self.window.minimumSize()
        self.assertGreaterEqual(min_size.width(), 1280)
        self.assertGreaterEqual(min_size.height(), 800)

        # 2. Sidebar contents margins
        margins = self.window.sidebar.layout().contentsMargins()
        self.assertEqual(margins.left(), 16)
        self.assertEqual(margins.top(), 10)
        self.assertEqual(margins.right(), 16)
        self.assertEqual(margins.bottom(), 16)

        # 3. Workspace table column resize modes
        ws = self.window.workspace_view
        header = ws.items_table.horizontalHeader()
        self.assertEqual(header.sectionResizeMode(0), QHeaderView.ResizeMode.Stretch)
        self.assertEqual(header.sectionResizeMode(1), QHeaderView.ResizeMode.ResizeToContents)
        self.assertEqual(header.sectionResizeMode(2), QHeaderView.ResizeMode.ResizeToContents)
        self.assertEqual(header.sectionResizeMode(3), QHeaderView.ResizeMode.ResizeToContents)
        self.assertEqual(header.sectionResizeMode(4), QHeaderView.ResizeMode.ResizeToContents)

        # 4. More Actions button and menu
        self.assertTrue(hasattr(ws, "btn_more_actions"))
        self.assertEqual(ws.btn_more_actions.text(), "More Actions ▾")
        menu = ws.btn_more_actions.menu()
        self.assertIsNotNone(menu)
        actions = menu.actions()
        action_texts = [a.text() for a in actions]
        self.assertTrue(any("Accept All" in t for t in action_texts))
        self.assertTrue(any("Attach File" in t for t in action_texts))
        self.assertTrue(any("Report Deficiency" in t for t in action_texts))
        self.assertTrue(any("Waive Requirement" in t for t in action_texts))

    def test_multi_row_selection_and_batch_processing(self):
        from unittest.mock import patch
        from src.clientdesk_ai.ui.qt_compat import QTableWidget, QTableWidgetSelectionRange
        from src.clientdesk_ai.domain.models import DocumentStatus

        ws = self.window.workspace_view
        # STEP 1: Verify selection behavior and mode
        self.assertEqual(ws.items_table.selectionBehavior(), QTableWidget.SelectionBehavior.SelectRows)
        self.assertEqual(ws.items_table.selectionMode(), QTableWidget.SelectionMode.ExtendedSelection)

        # Load engagement 1 checklist
        ws.selected_engagement_id = 1
        ws.load_engagement_checklist(1)
        self.assertGreaterEqual(ws.items_table.rowCount(), 2)

        # Select first two rows (simulating shift/drag multi-selection)
        ws.items_table.clearSelection()
        ws.items_table.setRangeSelected(QTableWidgetSelectionRange(0, 0, 1, 7), True)

        # STEP 2: Verify get_selected_item_ids returns both IDs
        selected_ids = ws.get_selected_item_ids()
        self.assertEqual(len(selected_ids), 2)
        self.assertEqual(ws.get_selected_item_id(), selected_ids[0])

        # STEP 3: Verify batch status update to RECEIVED
        with patch("src.clientdesk_ai.ui.views.engagement_workspace_view.QMessageBox.information") as mock_info:
            ws.update_selected_item_status(DocumentStatus.RECEIVED)
            mock_info.assert_called_once()
            self.assertIn("Successfully updated 2 items", mock_info.call_args[0][2])

        # Verify items in database
        items = self.window.engagement_repo.get_items(1)
        updated_items = [i for i in items if i.engagement_item_id in selected_ids]
        for itm in updated_items:
            self.assertEqual(itm.collection_status, DocumentStatus.RECEIVED)

        # STEP 4: Verify batch waive with single justification
        with patch("src.clientdesk_ai.ui.views.engagement_workspace_view.QInputDialog.getText", return_value=("Exempt statutory entity", True)), \
             patch("src.clientdesk_ai.ui.views.engagement_workspace_view.QMessageBox.information") as mock_info:
            # Re-select rows
            ws.items_table.clearSelection()
            ws.items_table.setRangeSelected(QTableWidgetSelectionRange(0, 0, 1, 7), True)
            ws.waive_selected_item()
            mock_info.assert_called_once()
            self.assertIn("Successfully waived 2 requirement(s)", mock_info.call_args[0][2])

        items_after_waive = self.window.engagement_repo.get_items(1)
        waived_items = [i for i in items_after_waive if i.engagement_item_id in selected_ids]
        for itm in waived_items:
            self.assertEqual(itm.collection_status, DocumentStatus.WAIVED_WITH_APPROVAL)
            self.assertEqual(itm.waiver_reason, "Exempt statutory entity")

        # STEP 5: Verify attach file rejects multiple selection
        with patch("src.clientdesk_ai.ui.views.engagement_workspace_view.QMessageBox.warning") as mock_warn:
            ws.items_table.clearSelection()
            ws.items_table.setRangeSelected(QTableWidgetSelectionRange(0, 0, 1, 7), True)
            ws.attach_file_to_selected_item()
            mock_warn.assert_called_once()
            self.assertIn("Please select only ONE row", mock_warn.call_args[0][2])


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestMainWindowUI)
    runner = unittest.TextTestRunner()
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
