"""Unit and integration tests for application services and workflows."""

import unittest
from pathlib import Path
import tempfile

from src.clientdesk_ai.config.settings import CONFIG
from src.clientdesk_ai.domain.models import (
    User, UserRole, Client, Engagement, DocumentStatus, RequirementType,
    ApplicabilityStatus, Priority, EngagementStatus
)
from src.clientdesk_ai.persistence.database import init_database
from src.clientdesk_ai.persistence.seed_data import seed_database
from src.clientdesk_ai.persistence.repositories import (
    UserRepository, ClientRepository, TemplateRepository, EngagementRepository,
    AttachmentRepository, LogRepository
)
from src.clientdesk_ai.application.services import (
    AuthService, ClientService, EngagementService, ChecklistService,
    AttachmentService, KnowledgeSearchService
)


class TestApplicationServices(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_clientdesk.db"
        self.filestore_path = Path(self.temp_dir.name) / "filestore"
        self.filestore_path.mkdir(parents=True, exist_ok=True)

        init_database(self.db_path)
        seed_database(self.db_path)

        self.user_repo = UserRepository(self.db_path)
        self.client_repo = ClientRepository(self.db_path)
        self.template_repo = TemplateRepository(self.db_path)
        self.engagement_repo = EngagementRepository(self.db_path)
        self.attachment_repo = AttachmentRepository(self.db_path)
        self.log_repo = LogRepository(self.db_path)

        self.auth_service = AuthService(self.user_repo, self.log_repo)
        self.client_service = ClientService(self.client_repo, self.log_repo)
        self.engagement_service = EngagementService(self.engagement_repo, self.template_repo, self.log_repo)
        self.checklist_service = ChecklistService(self.engagement_repo, self.log_repo)
        self.attachment_service = AttachmentService(self.attachment_repo, self.log_repo, self.filestore_path)
        self.search_service = KnowledgeSearchService(self.db_path)

        # Create test users
        self.admin_user = self.user_repo.get_by_username("admin")
        self.staff_id = self.user_repo.create_user(
            User(username="staff1", full_name="Staff Operator", email="staff1@test.com", password_hash="dummy", role=UserRole.STAFF)
        )
        self.staff_user = self.user_repo.get_by_id(self.staff_id)

        self.senior_id = self.user_repo.create_user(
            User(username="senior1", full_name="Senior Reviewer", email="senior1@test.com", password_hash="dummy", role=UserRole.SENIOR)
        )
        self.senior_user = self.user_repo.get_by_id(self.senior_id)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_client_registration_and_duplicate_check(self):
        client = Client(client_code="CLI001", client_name="Apex Enterprises", pan="ABCDE1234F")
        ok, created, msg = self.client_service.register_client(client, self.admin_user)
        self.assertTrue(ok)
        self.assertIsNotNone(created)

        # Duplicate client code rejected
        duplicate = Client(client_code="CLI001", client_name="Duplicate Co")
        dup_ok, _, dup_msg = self.client_service.register_client(duplicate, self.admin_user)
        self.assertFalse(dup_ok)
        self.assertIn("already exists", dup_msg)

    def test_engagement_creation_and_snapshot(self):
        # Register client
        client = Client(client_code="CLI002", client_name="Zenith Traders")
        _, created_client, _ = self.client_service.register_client(client, self.admin_user)

        # Create GST Registration engagement
        services = self.template_repo.list_services()
        gst_service = next(s for s in services if s.service_code == "GST_REG")

        eng = Engagement(
            client_id=created_client.client_id,
            service_id=gst_service.service_id,
            due_date="2026-11-30",
            assigned_to=self.staff_id,
            reviewer_id=self.senior_id
        )
        ok, eng_id, _ = self.engagement_service.create_engagement(eng, self.admin_user)
        self.assertTrue(ok)
        self.assertIsNotNone(eng_id)

        # Verify items were snapshotted
        items = self.engagement_repo.get_items(eng_id)
        self.assertGreater(len(items), 5)
        self.assertEqual(items[0].collection_status, DocumentStatus.NOT_REQUESTED)

    def test_readiness_calculation_and_review_workflow(self):
        # Setup client & engagement
        client = Client(client_code="CLI003", client_name="Blue Horizon")
        _, created_client, _ = self.client_service.register_client(client, self.admin_user)

        services = self.template_repo.list_services()
        gst_service = next(s for s in services if s.service_code == "GST_REG")

        eng = Engagement(
            client_id=created_client.client_id,
            service_id=gst_service.service_id,
            due_date="2026-11-30",
            assigned_to=self.staff_id,
            reviewer_id=self.senior_id
        )
        _, eng_id, _ = self.engagement_service.create_engagement(eng, self.admin_user)
        items = self.engagement_repo.get_items(eng_id)

        # Before accepting documents, readiness should be 0% and review submission blocked
        sub_ok, sub_msg = self.engagement_service.submit_for_review(eng_id, self.staff_user)
        self.assertFalse(sub_ok)
        self.assertIn("mandatory items remaining", sub_msg)

        # Mark all mandatory items as ACCEPTED
        for item in items:
            if item.requirement_snapshot == RequirementType.MANDATORY:
                self.checklist_service.update_item_status(item.engagement_item_id, DocumentStatus.ACCEPTED, self.staff_user)
            elif item.requirement_snapshot == RequirementType.CONDITIONAL:
                # Mark conditional as not applicable
                self.checklist_service.update_item_status(
                    item.engagement_item_id, DocumentStatus.NOT_APPLICABLE, self.staff_user,
                    applicability=ApplicabilityStatus.NOT_APPLICABLE
                )

        summary = self.engagement_service.get_readiness(eng_id)
        self.assertEqual(summary.readiness_percentage, 100.0)
        self.assertTrue(summary.is_ready_for_review)

        # Now submission for review should succeed
        sub_ok2, sub_msg2 = self.engagement_service.submit_for_review(eng_id, self.staff_user)
        self.assertTrue(sub_ok2)

        # Segregation of duties: Staff cannot approve their own engagement
        app_ok_staff, _ = self.engagement_service.perform_review(eng_id, self.staff_user, True, "Staff self-approving")
        self.assertFalse(app_ok_staff)

        # Senior reviewer approval succeeds
        app_ok_senior, _ = self.engagement_service.perform_review(eng_id, self.senior_user, True, "All compliance verified")
        self.assertTrue(app_ok_senior)

    def test_waiver_requires_authorized_role_and_reason(self):
        client = Client(client_code="CLI004", client_name="Omega Tech")
        _, created_client, _ = self.client_service.register_client(client, self.admin_user)
        services = self.template_repo.list_services()
        eng = Engagement(client_id=created_client.client_id, service_id=services[0].service_id, due_date="2026-12-15")
        _, eng_id, _ = self.engagement_service.create_engagement(eng, self.admin_user)
        items = self.engagement_repo.get_items(eng_id)
        target_item = items[0]

        # Staff cannot waive without authority
        ok_staff, _ = self.checklist_service.update_item_status(
            target_item.engagement_item_id, DocumentStatus.WAIVED_WITH_APPROVAL, self.staff_user,
            waiver_reason="Client requested waiver"
        )
        self.assertFalse(ok_staff)

        # Senior waiving without reason fails
        ok_no_reason, _ = self.checklist_service.update_item_status(
            target_item.engagement_item_id, DocumentStatus.WAIVED_WITH_APPROVAL, self.senior_user,
            waiver_reason=""
        )
        self.assertFalse(ok_no_reason)

        # Senior waiving with reason succeeds
        ok_valid, _ = self.checklist_service.update_item_status(
            target_item.engagement_item_id, DocumentStatus.WAIVED_WITH_APPROVAL, self.senior_user,
            waiver_reason="Entity has special statutory exemption u/s 12A"
        )
        self.assertTrue(ok_valid)

    def test_file_attachment_and_duplicate_detection(self):
        # Create a test dummy file
        test_file = Path(self.temp_dir.name) / "electricity_bill.pdf"
        test_file.write_text("DUMMY_PDF_CONTENT_ELECTRICITY_BILL_OCTOBER")

        client = Client(client_code="CLI005", client_name="Solace Logistics")
        _, created_client, _ = self.client_service.register_client(client, self.admin_user)
        services = self.template_repo.list_services()
        eng = Engagement(client_id=created_client.client_id, service_id=services[0].service_id, due_date="2026-12-15")
        _, eng_id, _ = self.engagement_service.create_engagement(eng, self.admin_user)
        items = self.engagement_repo.get_items(eng_id)

        # Attach file
        ok, att, msg = self.attachment_service.attach_file(test_file, items[0].engagement_item_id, self.staff_user)
        self.assertTrue(ok)
        self.assertIsNotNone(att)

        # Re-uploading identical file to the same item must be blocked
        ok_dup, att_dup, msg_dup = self.attachment_service.attach_file(test_file, items[0].engagement_item_id, self.staff_user)
        self.assertFalse(ok_dup)
        self.assertIsNone(att_dup)
        self.assertIn("This exact file has already been uploaded for this checklist item", msg_dup)

        # Uploading the same file to a different item is permitted
        ok2, att2, msg2 = self.attachment_service.attach_file(test_file, items[1].engagement_item_id, self.staff_user)
        self.assertTrue(ok2)
        self.assertIsNotNone(att2)

    def test_offline_knowledge_search_fts5(self):
        results = self.search_service.search("AOC-4")
        self.assertGreater(len(results), 0)
        self.assertIn("MCA Annual Filing", results[0]["title"])

        results_gst = self.search_service.search("threshold")
        self.assertGreater(len(results_gst), 0)
        self.assertIn("GST Registration", results_gst[0]["title"])

    def test_client_optional_identifiers_and_statutory_validation(self):
        # 1. All identifiers are optional (empty strings succeed)
        c_empty = Client(client_code="OPT001", client_name="Optional Identifiers Corp")
        ok, created, msg = self.client_service.register_client(c_empty)  # Also tests actor=None default!
        self.assertTrue(ok)
        self.assertIsNotNone(created)

        # 2. PAN validation: must be 5 letters + 4 digits + 1 letter
        c_bad_pan = Client(client_code="OPT002", client_name="Bad PAN Co", pan="12345ABCDE")
        ok, _, msg = self.client_service.register_client(c_bad_pan)
        self.assertFalse(ok)
        self.assertIn("Invalid PAN format", msg)

        # 3. Aadhaar validation: must be exactly 12 numerical digits
        c_bad_aadhaar = Client(client_code="OPT003", client_name="Bad Aadhaar Co", aadhaar="1234ABCD9012")
        ok, _, msg = self.client_service.register_client(c_bad_aadhaar)
        self.assertFalse(ok)
        self.assertIn("Invalid Aadhaar format", msg)

        # 4. GSTIN validation: must be 15 alphanumeric matching PAN
        c_bad_gstin = Client(client_code="OPT004", client_name="Bad GSTIN Co", gstin="27ABCDE123")
        ok, _, msg = self.client_service.register_client(c_bad_gstin)
        self.assertFalse(ok)
        self.assertIn("Invalid GSTIN format", msg)

        # 5. GSTIN mismatch with PAN
        c_mismatch = Client(client_code="OPT005", client_name="Mismatch Co", pan="ABCDE1234F", gstin="27ZZZZZ9999Z1Z5")
        ok, _, msg = self.client_service.register_client(c_mismatch)
        self.assertFalse(ok)
        self.assertIn("does not match PAN", msg)

        # 6. Valid PAN + Aadhaar + GSTIN succeeds
        c_valid = Client(
            client_code="OPT006",
            client_name="Valid Compliance Co",
            pan="ABCDE1234F",
            aadhaar="1234 5678 9012",
            gstin="27ABCDE1234F1Z5"
        )
        ok, created_valid, msg = self.client_service.register_client(c_valid, self.admin_user)
        self.assertTrue(ok)
        self.assertEqual(created_valid.pan, "ABCDE1234F")
        self.assertEqual(created_valid.aadhaar, "123456789012")
        self.assertEqual(created_valid.gstin, "27ABCDE1234F1Z5")


if __name__ == "__main__":
    unittest.main()
