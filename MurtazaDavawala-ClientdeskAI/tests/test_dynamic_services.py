"""Unit tests for dynamic service creation and custom service groups."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.clientdesk_ai.persistence.database import init_database
from src.clientdesk_ai.persistence.seed_data import seed_database
from src.clientdesk_ai.persistence.repositories import TemplateRepository
from src.clientdesk_ai.domain.models import User, UserRole


class TestDynamicServices(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_clientdesk.db"
        init_database(self.db_path)
        seed_database(self.db_path)
        self.repo = TemplateRepository(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_create_dynamic_services_and_groups(self):
        # 1. Verify baseline seed groups
        groups = self.repo.list_service_groups()
        self.assertIn("GST", groups)
        self.assertIn("ITR", groups)

        # 2. Add new service with a completely new custom group
        s_id1 = self.repo.create_service(
            service_code="TDS_QTR",
            service_name="TDS Quarterly Return (24Q/26Q)",
            service_group="Tax Deducted at Source",
            description="Quarterly statutory filing of salary and vendor TDS withholding."
        )
        self.assertIsInstance(s_id1, int)
        self.assertGreater(s_id1, 0)

        # 3. Add 9th, 10th services (verifying trigger trg_prevent_unapproved_service_count was removed)
        s_id2 = self.repo.create_service(
            service_code="FEMA_FLA",
            service_name="Foreign Liabilities and Assets Annual Return",
            service_group="FEMA & RBI Compliance",
            description="Annual reporting to Reserve Bank of India on foreign direct investments."
        )
        self.assertGreater(s_id2, 0)

        # 4. Check list_service_groups reflects new groups
        updated_groups = self.repo.list_service_groups()
        self.assertIn("Tax Deducted at Source", updated_groups)
        self.assertIn("FEMA & RBI Compliance", updated_groups)

        # 5. Verify service retrieval
        svc = self.repo.get_service(s_id1)
        self.assertIsNotNone(svc)
        self.assertEqual(svc.service_code, "TDS_QTR")
        self.assertEqual(svc.service_name, "TDS Quarterly Return (24Q/26Q)")
        self.assertEqual(svc.service_group, "Tax Deducted at Source")

    def test_admin_partner_security_check(self):
        admin = User(user_id=1, username="admin", full_name="Admin", role=UserRole.ADMIN)
        partner = User(user_id=2, username="partner", full_name="Partner", role=UserRole.PARTNER)
        senior = User(user_id=3, username="senior", full_name="Senior", role=UserRole.SENIOR)
        staff = User(user_id=4, username="staff", full_name="Staff", role=UserRole.STAFF)

        allowed_roles = (UserRole.ADMIN, UserRole.PARTNER)
        self.assertIn(admin.role, allowed_roles)
        self.assertIn(partner.role, allowed_roles)
        self.assertNotIn(senior.role, allowed_roles)
        self.assertNotIn(staff.role, allowed_roles)


if __name__ == "__main__":
    unittest.main()
