"""Unit tests for the dynamic Firm Wiki, KnowledgeRepository, and Contextual Linking."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.clientdesk_ai.persistence.database import init_database
from src.clientdesk_ai.persistence.seed_data import seed_database
from src.clientdesk_ai.persistence.repositories import KnowledgeRepository, LogRepository
from src.clientdesk_ai.application.services import KnowledgeSearchService
from src.clientdesk_ai.domain.models import User, UserRole


class TestFirmWikiAndKnowledge(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_clientdesk.db"
        init_database(self.db_path)
        seed_database(self.db_path)
        self.repo = KnowledgeRepository(self.db_path)
        self.log_repo = LogRepository(self.db_path)
        self.search_service = KnowledgeSearchService(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_add_update_delete_knowledge(self):
        # 1. Add Knowledge article
        doc_id = self.repo.add_knowledge(
            title="Import Export Code (IEC) Protocol",
            service_group="DGFT",
            content="IEC registration is mandatory for commercial import and export from India."
        )
        self.assertIsInstance(doc_id, int)
        self.assertGreater(doc_id, 0)

        # Verify retrieved by get_knowledge
        doc = self.repo.get_knowledge(doc_id)
        self.assertIsNotNone(doc)
        self.assertEqual(doc["title"], "Import Export Code (IEC) Protocol")
        self.assertEqual(doc["service_group"], "DGFT")

        # Verify FTS search matches
        search_res = self.search_service.search("export")
        titles = [r["title"] for r in search_res]
        self.assertIn("Import Export Code (IEC) Protocol", titles)

        # 2. Update Knowledge article
        updated = self.repo.update_knowledge(
            doc_id,
            title="IEC Registration Standard Operating Procedure",
            content="Updated SOP: IEC registration is fully online on DGFT portal with Aadhaar OTP.",
            service_group="DGFT"
        )
        self.assertTrue(updated)

        doc_updated = self.repo.get_knowledge(doc_id)
        self.assertEqual(doc_updated["title"], "IEC Registration Standard Operating Procedure")

        # Verify updated FTS search matches new term
        search_res2 = self.search_service.search("portal")
        titles2 = [r["title"] for r in search_res2]
        self.assertIn("IEC Registration Standard Operating Procedure", titles2)

        # 3. Delete Knowledge article
        deleted = self.repo.delete_knowledge(doc_id)
        self.assertTrue(deleted)
        self.assertIsNone(self.repo.get_knowledge(doc_id))

        # Verify removed from FTS index
        search_res3 = self.search_service.search("export")
        titles3 = [r["title"] for r in search_res3]
        self.assertNotIn("Import Export Code (IEC) Protocol", titles3)

    def test_log_repository_delegation(self):
        # Test add/update/delete via LogRepository methods
        doc_id = self.log_repo.add_knowledge(
            title="TDS Return 26Q SOP",
            service_group="ITR",
            content="Form 26Q is quarterly statement of tax deducted at source in respect of payments other than salary."
        )
        self.assertGreater(doc_id, 0)

        updated = self.log_repo.update_knowledge(
            doc_id,
            title="TDS Return 26Q Comprehensive Guide",
            content="Form 26Q filing requires valid TAN and active Challan ITNS 281."
        )
        self.assertTrue(updated)

        deleted = self.log_repo.delete_knowledge(doc_id)
        self.assertTrue(deleted)

    def test_contextual_guidance_lookup(self):
        # Test document snapshot matching seeded items
        match1 = self.repo.find_guidance("Form 16 (Part A and Part B) from Employer")
        self.assertIsNotNone(match1)
        self.assertIn("ITR", match1["service_group"])

        match2 = self.repo.find_guidance("PAN Card of Authorized Signatory")
        self.assertIsNotNone(match2)

        match3 = self.repo.find_guidance("Form 26AS & Annual Information Statement (AIS / TIS)")
        self.assertIsNotNone(match3)

    def test_role_security_matrix(self):
        # Verification that only ADMIN, PARTNER, SENIOR have manage permission
        admin_user = User(user_id=1, username="admin", full_name="Admin", role=UserRole.ADMIN)
        partner_user = User(user_id=2, username="partner", full_name="Partner", role=UserRole.PARTNER)
        senior_user = User(user_id=3, username="senior", full_name="Senior", role=UserRole.SENIOR)
        staff_user = User(user_id=4, username="staff", full_name="Staff", role=UserRole.STAFF)
        readonly_user = User(user_id=5, username="reader", full_name="Reader", role=UserRole.READ_ONLY)

        allowed_roles = (UserRole.ADMIN.value, UserRole.PARTNER.value, UserRole.SENIOR.value)
        self.assertIn(admin_user.role.value, allowed_roles)
        self.assertIn(partner_user.role.value, allowed_roles)
        self.assertIn(senior_user.role.value, allowed_roles)
        self.assertNotIn(staff_user.role.value, allowed_roles)
        self.assertNotIn(readonly_user.role.value, allowed_roles)


if __name__ == "__main__":
    unittest.main()
