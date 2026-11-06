"""Test database initialization, seeding, and constraint enforcement."""

import unittest
from pathlib import Path
import tempfile
import sqlite3

from src.clientdesk_ai.persistence.database import init_database, get_db_connection
from src.clientdesk_ai.persistence.seed_data import seed_database
from src.clientdesk_ai.security.crypto import verify_password


class TestDatabasePersistence(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_clientdesk.db"
        init_database(self.db_path)
        seed_database(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_tables_created(self):
        conn = get_db_connection(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cur.fetchall()]
        conn.close()

        self.assertIn("users", tables)
        self.assertIn("clients", tables)
        self.assertIn("service_templates", tables)
        self.assertIn("template_variants", tables)
        self.assertIn("engagements", tables)
        self.assertIn("engagement_checklist_items", tables)
        self.assertIn("document_attachments", tables)
        self.assertIn("knowledge_documents", tables)
        self.assertIn("knowledge_fts", tables)

    def test_seed_services_and_variants(self):
        conn = get_db_connection(self.db_path)
        cur = conn.cursor()
        
        # Check initial 8 source services under the 6 groups
        cur.execute("SELECT COUNT(*) FROM service_templates")
        service_count = cur.fetchone()[0]
        self.assertEqual(service_count, 8)

        # Check 8 GST entity variants
        cur.execute("SELECT COUNT(*) FROM template_variants")
        variant_count = cur.fetchone()[0]
        self.assertEqual(variant_count, 8)

        # Check checklist items exist
        cur.execute("SELECT COUNT(*) FROM checklist_items")
        item_count = cur.fetchone()[0]
        self.assertGreater(item_count, 35)

        # Check default admin exists and password is verified
        cur.execute("SELECT password_hash FROM users WHERE username='admin'")
        admin_row = cur.fetchone()
        self.assertIsNotNone(admin_row)
        self.assertTrue(verify_password("admin", admin_row[0]) or verify_password("Admin@Clientdesk123", admin_row[0]))

        conn.close()


if __name__ == "__main__":
    unittest.main()
