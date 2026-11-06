"""Initial database seeding for roles, approved 6 service groups, variants, and checklist items."""

from datetime import datetime, timezone
import sqlite3
from typing import Optional
from pathlib import Path

from src.clientdesk_ai.config.settings import CONFIG
from src.clientdesk_ai.persistence.database import get_db_connection
from src.clientdesk_ai.security.crypto import hash_password

INITIAL_ROLES = [
    ("ADMIN", "System administrator with full configuration and user access"),
    ("PARTNER", "Partner/Principal with firm oversight, reporting, and final sign-offs"),
    ("SENIOR", "Senior reviewer for checking document completeness and compliance"),
    ("STAFF", "Accountant/Staff responsible for document collection and verification"),
    ("READ_ONLY", "View-only access to assigned records"),
]

INITIAL_SERVICES = [
    ("GST_REG", "GST Registration", "GST", "New Goods and Services Tax registration for various business constitutions"),
    ("GST_ANNUAL", "GST Annual Return (GSTR-9 & 9C)", "GST", "Annual return compilation, reconciliation, and audit reporting"),
    ("ITR_SALARIED", "ITR — Individual (Salaried)", "ITR", "Income tax return filing for salaried individuals (ITR-1 / ITR-2)"),
    ("ITR_BUSINESS", "ITR — Business / Firm / Professional", "ITR", "Income tax return for proprietary business, firms, and professionals (ITR-3 / ITR-4)"),
    ("COMPANY_INC", "Company Incorporation (Pvt Ltd / OPC)", "Company Formation", "Incorporation of Private Limited Company or One Person Company on MCA SPICe+"),
    ("PARTNERSHIP_REG", "Partnership Firm Registration", "Partnership Registration", "Drafting deed and registration with Registrar of Firms (ROF)"),
    ("LLP_INC", "LLP Incorporation", "LLP Incorporation", "Limited Liability Partnership formation and MCA filing"),
    ("MCA_ANNUAL", "ROC / MCA Annual Compliance", "MCA Annual Compliance", "Annual ROC filings including AOC-4, MGT-7, and director KYC"),
]

GST_VARIANTS = [
    ("SOLE_PROP", "Sole Proprietorship", "Individual proprietary trading or service business"),
    ("PARTNERSHIP", "Partnership Firm", "Registered or unregistered partnership firm"),
    ("PVT_LTD", "Private / Public Limited Company", "Incorporated corporate entity"),
    ("LLP", "LLP (Limited Liability Partnership)", "Incorporated partnership under LLP Act"),
    ("HUF", "HUF (Hindu Undivided Family)", "Hindu Undivided Family business entity"),
    ("TRUST", "Trust / Society / Club / AOP", "Non-profit or association of persons"),
    ("GOVT", "Government Department / PSU", "Government body or public sector undertaking"),
    ("CASUAL", "Casual Taxable Person", "Temporary business presence in a taxable jurisdiction"),
]

# Standardized checklist document definitions for the initial services.
#
# Tuple structure (8 fields):
#   (category, document_name, requirement_type, guidance_note, display_order,
#    variant_codes_or_None, file_formats, format_instructions)
#
# variant_codes_or_None:
#   - None  → applies to ALL variants (universal item)
#   - tuple → applies ONLY to those specific variant codes
#
SERVICE_CHECKLISTS = {
    "GST_REG": [
        # (cat, doc, req, note, order, variants, file_formats, format_instructions)
        ("Identity Proof", "PAN Card of Applicant / Entity", "MANDATORY",
         "Clear color scan required", 1,
         None, "PDF, JPG", "Color scan, both sides, max 2 MB, min 200 DPI"),

        ("Identity Proof", "Aadhaar Card of Applicant / Authorised Signatory", "MANDATORY",
         "Linked mobile required for OTP e-sign", 2,
         None, "PDF, JPG", "Color scan, both sides, max 2 MB — ensure 12-digit number is legible"),

        ("Address Proof", "Electricity Bill / Municipal Tax Receipt of Business Place", "MANDATORY",
         "Not older than 2 months", 3,
         None, "PDF, JPG", "Full bill — account name + address page, max 3 MB"),

        ("Address Proof", "Rent Agreement / NOC from Property Owner", "CONDITIONAL",
         "Required if premises is rented/leased", 4,
         None, "PDF", "Registered/notarised copy preferred, all pages, max 5 MB"),

        ("Banking Proof", "Cancelled Cheque / Bank Statement showing Name & IFSC", "MANDATORY",
         "Bank account must be in business/applicant name", 5,
         None, "PDF, JPG", "Cheque scan or first page of statement, max 2 MB"),

        # Board Resolution — only for PVT_LTD and LLP variants
        ("Authorization", "Board Resolution / Letter of Authorisation", "CONDITIONAL",
         "Mandatory for Companies and LLPs", 6,
         ("PVT_LTD", "LLP"), "PDF", "Signed by directors/partners on letterhead, company seal, max 2 MB"),

        ("Photographs", "Passport Size Photograph of Applicant / Promoters", "MANDATORY",
         "White background color photograph", 7,
         None, "JPG, PNG", "Recent photo, white background, 35x45 mm, max 100 KB per photo"),
    ],
    "GST_ANNUAL": [
        ("Financials", "Audited Financial Statements (Balance Sheet & P&L)", "MANDATORY",
         "Complete signed financial statements", 1,
         None, "PDF", ""),

        ("GST Records", "Monthly GSTR-1 and GSTR-3B filed returns summary", "MANDATORY",
         "Consolidated returns for FY", 2,
         None, "PDF, XLSX", ""),

        ("Reconciliation", "GSTR-2B / 2A Input Tax Credit vs Purchase Register", "MANDATORY",
         "Detailed vendor-wise ITC reconciliation", 3,
         None, "PDF, XLSX", ""),

        ("Tax Audit", "Form 3CD Tax Audit Report (if applicable)", "CONDITIONAL",
         "Applicable if turnover exceeds statutory threshold", 4,
         None, "PDF", ""),

        ("E-Way Bills", "E-Way Bill vs Outward Register reconciliation", "OPTIONAL",
         "Cross-check report", 5,
         None, "PDF, XLSX", ""),
    ],
    "ITR_SALARIED": [
        ("Salary", "Form 16 (Part A and Part B) from Employer", "MANDATORY",
         "Signed certificate of tax deducted at source", 1,
         None, "PDF", "Password-protected PDF if issued digitally; provide password separately"),

        ("Tax Statements", "Form 26AS & Annual Information Statement (AIS / TIS)", "MANDATORY",
         "Downloaded from Income Tax portal", 2,
         None, "PDF", "Full document — do not crop pages"),

        ("Banking", "Bank Statements for all active bank accounts for FY", "MANDATORY",
         "April 1 to March 31 statements", 3,
         None, "PDF", "All months April–March, passbook or portal statement"),

        ("Deductions", "Proof of Investments (LIC, PPF, ELSS, NPS, Mediclaim)", "CONDITIONAL",
         "If claiming Chapter VI-A deductions under old regime", 4,
         None, "PDF, JPG", ""),

        ("Housing Loan", "Home Loan Interest and Principal Repayment Certificate", "CONDITIONAL",
         "For interest deduction u/s 24(b)", 5,
         None, "PDF", ""),

        ("Capital Gains", "Capital Gains statement from Stock Broker / Mutual Fund", "CONDITIONAL",
         "If equity or mutual fund transactions occurred", 6,
         None, "PDF, XLSX", ""),
    ],
    "ITR_BUSINESS": [
        ("Financials", "Balance Sheet, Profit & Loss Account and Trial Balance", "MANDATORY",
         "Complete financial records for FY", 1,
         None, "PDF, XLSX", ""),

        ("Tax Statements", "Form 26AS, AIS and TIS", "MANDATORY",
         "Verified against books of account", 2,
         None, "PDF", ""),

        ("Banking", "Bank Account Statements for all Current & Savings accounts", "MANDATORY",
         "For complete financial year", 3,
         None, "PDF", ""),

        ("GST Reconciliation", "GST Turnover Reconciliation with Turnover in Books", "MANDATORY",
         "Reconcile reported turnover", 4,
         None, "PDF, XLSX", ""),

        ("Audit Reports", "Tax Audit Report u/s 44AB (if turnover exceeds limit)", "CONDITIONAL",
         "Mandatory if statutory audit triggered", 5,
         None, "PDF", ""),

        ("Fixed Assets", "Fixed Asset Addition/Deletion Invoices for Depreciation", "CONDITIONAL",
         "To claim depreciation as per IT Act", 6,
         None, "PDF, JPG", ""),
    ],
    "COMPANY_INC": [
        ("Promoter Identity", "PAN Card of all Directors and Shareholders", "MANDATORY",
         "Self-attested copy", 1,
         None, "PDF, JPG", "Color scan, self-attested with signature and date, max 2 MB per PAN"),

        ("Promoter Identity", "Aadhaar Card / Voter ID / Passport of all Promoters", "MANDATORY",
         "Self-attested identity proof", 2,
         None, "PDF, JPG", "Self-attested, max 2 MB per document"),

        ("Address Proof", "Bank Statement / Electricity Bill of Promoters (< 2 months)", "MANDATORY",
         "Address must match official records", 3,
         None, "PDF, JPG", ""),

        ("Registered Office", "Electricity / Utility Bill of Registered Office (< 2 months)", "MANDATORY",
         "In name of owner", 4,
         None, "PDF, JPG", ""),

        ("Registered Office", "Rent Agreement and Owner NOC for Registered Office", "MANDATORY",
         "Signed by owner with title proof", 5,
         None, "PDF", ""),

        ("Corporate Documents", "Draft Memorandum of Association (MOA) & Articles (AOA)", "MANDATORY",
         "Objectives aligned with MCA guidelines", 6,
         None, "PDF", ""),

        ("Director KYC", "DIR-2 Consent and INC-9 Declaration from Directors", "MANDATORY",
         "Prescribed MCA format", 7,
         None, "PDF", ""),
    ],
    "PARTNERSHIP_REG": [
        ("Deed", "Partnership Deed drafted and executed on Stamp Paper", "MANDATORY",
         "Signed by all partners with witnesses", 1,
         None, "PDF", ""),

        ("Partner Identity", "PAN and Aadhaar Cards of all Partners", "MANDATORY",
         "Self-attested copies", 2,
         None, "PDF, JPG", ""),

        ("Partner Address", "Residential Address Proof of all Partners", "MANDATORY",
         "Bank statement or utility bill", 3,
         None, "PDF, JPG", ""),

        ("Place of Business", "Address proof and Rent Agreement of Principal Place of Business", "MANDATORY",
         "Along with NOC from property owner", 4,
         None, "PDF", ""),

        ("ROF Form", "Form 1 Application for Registration of Firm", "MANDATORY",
         "Signed and notarized/attested", 5,
         None, "PDF", ""),
    ],
    "LLP_INC": [
        ("Partner Identity", "PAN Card & Aadhaar/Passport of Designated Partners", "MANDATORY",
         "Self-attested copies", 1,
         None, "PDF, JPG", ""),

        ("Partner Address", "Bank Statement or Utility Bill of Designated Partners", "MANDATORY",
         "Not older than 2 months", 2,
         None, "PDF, JPG", ""),

        ("Registered Office", "Registered Office Proof (Utility Bill + NOC + Rent Deed)", "MANDATORY",
         "Complete premises documentation", 3,
         None, "PDF", ""),

        ("MCA Name Approval", "RUN-LLP Name Approval Notice", "MANDATORY",
         "Approved name letter from MCA", 4,
         None, "PDF", ""),

        ("LLP Agreement", "Draft LLP Agreement to be filed in Form 3", "MANDATORY",
         "Executed within 30 days of incorporation", 5,
         None, "PDF", ""),

        ("Partner Consent", "Consent to act as Designated Partner (Form 9)", "MANDATORY",
         "Signed by all partners", 6,
         None, "PDF", ""),
    ],
    "MCA_ANNUAL": [
        ("Financials", "Audited Balance Sheet, P&L, Notes, and Director's Report", "MANDATORY",
         "Signed by directors and statutory auditor", 1,
         None, "PDF", ""),

        ("Annual Return", "List of Shareholders and Transfer Register for Form MGT-7", "MANDATORY",
         "Shareholding details as on March 31", 2,
         None, "PDF, XLSX", ""),

        ("Auditor Appointment", "Form ADT-1 copy of Auditor Appointment", "MANDATORY",
         "To confirm auditor tenure validity", 3,
         None, "PDF", ""),

        ("Director KYC", "DIR-3 KYC verification status of all Directors", "MANDATORY",
         "Active DIN status required", 4,
         None, "PDF", ""),

        ("Secretarial Audit", "Form MR-3 Secretarial Audit Report (if applicable)", "CONDITIONAL",
         "Mandatory for specified threshold companies", 5,
         None, "PDF", ""),

        ("Cost Audit", "Form CRA-4 Cost Audit Report (if applicable)", "CONDITIONAL",
         "Mandatory for regulated sector companies", 6,
         None, "PDF", ""),
    ],
}

KNOWLEDGE_BASE_ITEMS = [
    ("GST Registration Overview & Checklist", "GST", "SOP", 
     "GST registration is mandatory for businesses exceeding turnover thresholds (Rs 40 Lakhs for goods, Rs 20 Lakhs for services in normal category states). Mandatory documents include PAN, Aadhaar of authorized signatory, bank proof, and proof of principal place of business. For rented premises, rent agreement and owner NOC are strictly required."),
    ("GSTR-9 and GSTR-9C Annual Compliance", "GST", "SOP",
     "GSTR-9 is the annual return for regular taxpayers. GSTR-9C is a self-certified reconciliation statement between audited annual financial statements and GSTR-9. Key focus areas: vendor ITC reconciliation with GSTR-2B, reporting outward taxable supplies, and discharging any reversal under Rule 42/43 via DRC-03."),
    ("Individual Salaried ITR Filing Guidelines", "ITR", "SOP",
     "ITR-1 (Sahaj) applies to resident individuals having total income up to Rs 50 Lakhs from Salary, one House Property, and Other Sources. For capital gains or multiple house properties, ITR-2 must be filed. Always cross-verify Form 16 figures with Form 26AS, AIS, and TIS before submission."),
    ("Business and Professional Tax Filing (ITR-3 / ITR-4)", "ITR", "SOP",
     "ITR-4 (Sugam) is for presumptive taxation under sections 44AD (business, 6%/8% turnover), 44ADA (professionals, 50% gross receipts), or 44AE. ITR-3 applies to individuals/HUFs with regular business books. Reconcile GST turnover with IT turnover and ensure bank balances reflect recorded cash flows."),
    ("Company Incorporation via SPICe+ (Part A & B)", "Company Formation", "SOP",
     "SPICe+ Part A covers name reservation; Part B integrates incorporation, DIN allotment, PAN, TAN, EPFO, ESIC, Professional Tax, and bank account opening. Mandatory attachments include INC-9 declaration, DIR-2 consent, utility bill not older than 2 months, and proof of identity/address of all subscribers."),
    ("MCA Annual Filing Requirements (AOC-4 & MGT-7)", "MCA Annual Compliance", "SOP",
     "Companies must hold AGM within 6 months of FY end. Form AOC-4 (Financial Statements) must be filed within 30 days of AGM. Form MGT-7/7A (Annual Return) must be filed within 60 days of AGM. Director KYC (DIR-3 KYC) must be completed before September 30 annually."),
    ("Firm SOP Wiki & Compliance Knowledge Base", "General Compliance", "SOP",
     "Welcome to the Firm Wiki & SOP Knowledge Base. This centralized repository contains official standard operating procedures (SOP), statutory filing rules, compliance checklists, documentation standards, and verification guidelines for statutory disciplines including GST, Income Tax (ITR), Company Formation, MCA Annual Compliance, LLP, and Audits. All staff, seniors, and partners must adhere to these firm guidelines."),
]


def seed_database(db_path: Optional[Path] = None) -> None:
    """Populate database with default roles, templates, variants, and knowledge documents."""
    conn = get_db_connection(db_path)
    now = datetime.now(timezone.utc).isoformat()
    try:
        with conn:
            # 1. Seed Roles
            for role_name, desc in INITIAL_ROLES:
                conn.execute(
                    "INSERT OR IGNORE INTO roles (role_name, description) VALUES (?, ?);",
                    (role_name, desc)
                )

            # 2. Seed Default Accounts (admin/admin, staff/staff, senior/senior)
            admin_pass_hash = hash_password("admin")
            admin_row = conn.execute("SELECT user_id FROM users WHERE username = 'admin';").fetchone()
            if not admin_row:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO users (username, full_name, email, password_hash, role, is_active, created_at)
                    VALUES (?, ?, ?, ?, ?, 1, ?);
                    """,
                    ("admin", "Default Administrator", "admin@clientdesk.local", admin_pass_hash, "ADMIN", now)
                )
            else:
                conn.execute(
                    "UPDATE users SET password_hash = ? WHERE username = 'admin';",
                    (admin_pass_hash,)
                )

            # Seed default staff user if none exists
            staff_row = conn.execute("SELECT user_id FROM users WHERE username = 'staff';").fetchone()
            if not staff_row:
                staff_pass_hash = hash_password("staff")
                conn.execute(
                    """
                    INSERT OR IGNORE INTO users (username, full_name, email, password_hash, role, is_active, created_at)
                    VALUES (?, ?, ?, ?, ?, 1, ?);
                    """,
                    ("staff", "Staff Operator", "staff@clientdesk.local", staff_pass_hash, "STAFF", now)
                )

            # Seed default senior reviewer if none exists
            senior_row = conn.execute("SELECT user_id FROM users WHERE username = 'senior';").fetchone()
            if not senior_row:
                senior_pass_hash = hash_password("senior")
                conn.execute(
                    """
                    INSERT OR IGNORE INTO users (username, full_name, email, password_hash, role, is_active, created_at)
                    VALUES (?, ?, ?, ?, ?, 1, ?);
                    """,
                    ("senior", "Senior Reviewer", "senior@clientdesk.local", senior_pass_hash, "SENIOR", now)
                )

            # 3. Seed the 6 Approved Service Groups & Templates
            for s_code, s_name, s_group, s_desc in INITIAL_SERVICES:
                s_row = conn.execute("SELECT service_id FROM service_templates WHERE service_code = ?;", (s_code,)).fetchone()
                if not s_row:
                    conn.execute(
                        """
                        INSERT INTO service_templates (service_code, service_name, service_group, description, is_active, created_at)
                        VALUES (?, ?, ?, ?, 1, ?);
                        """,
                        (s_code, s_name, s_group, s_desc, now)
                    )
                    s_row = conn.execute("SELECT service_id FROM service_templates WHERE service_code = ?;", (s_code,)).fetchone()

                if not s_row:
                    continue
                service_id = s_row["service_id"]

                # Ensure template_versions has at least version 1 approved
                conn.execute(
                    """
                    INSERT OR IGNORE INTO template_versions (service_id, version_number, status, effective_from, approved_at)
                    VALUES (?, 1, 'APPROVED', '2026-04-01', ?);
                    """,
                    (service_id, now)
                )

                # Seed GST Variants specifically for GST Registration
                if s_code == "GST_REG":
                    for v_code, v_name, v_desc in GST_VARIANTS:
                        v_row = conn.execute("SELECT variant_id FROM template_variants WHERE service_id = ? AND variant_code = ?;", (service_id, v_code)).fetchone()
                        if not v_row:
                            conn.execute(
                                """
                                INSERT INTO template_variants (service_id, variant_code, variant_name, description, is_active)
                                VALUES (?, ?, ?, ?, 1);
                                """,
                                (service_id, v_code, v_name, v_desc)
                            )

                # Seed Checklist items if not already present
                items = SERVICE_CHECKLISTS.get(s_code, [])
                for item_tuple in items:
                    # Support both legacy 5-tuple and new 8-tuple format
                    if len(item_tuple) == 8:
                        cat, doc_name, req_type, note, order, variant_codes, file_fmts, fmt_instr = item_tuple
                    else:
                        cat, doc_name, req_type, note, order = item_tuple
                        variant_codes, file_fmts, fmt_instr = None, "PDF, JPG", ""

                    # Check if already seeded (match by service_id + document_name)
                    existing = conn.execute(
                        "SELECT item_id FROM checklist_items WHERE service_id = ? AND document_name = ?;",
                        (service_id, doc_name)
                    ).fetchone()
                    if existing:
                        # Update format fields if columns exist (migration)
                        conn.execute(
                            """
                            UPDATE checklist_items
                            SET file_formats = ?, format_instructions = ?
                            WHERE item_id = ?;
                            """,
                            (file_fmts, fmt_instr, existing["item_id"])
                        )
                        continue

                    if variant_codes is None:
                        # Universal item — no variant restriction
                        conn.execute(
                            """
                            INSERT INTO checklist_items
                                (service_id, variant_id, category_name, document_name, requirement_type,
                                 guidance_note, file_formats, format_instructions, display_order, is_active)
                            VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, 1);
                            """,
                            (service_id, cat, doc_name, req_type, note, file_fmts, fmt_instr, order)
                        )
                    else:
                        # Variant-specific item — insert one row per applicable variant
                        for v_code in variant_codes:
                            v_row = conn.execute(
                                "SELECT variant_id FROM template_variants WHERE service_id = ? AND variant_code = ?;",
                                (service_id, v_code)
                            ).fetchone()
                            if not v_row:
                                continue
                            vid = v_row["variant_id"]
                            # Check not already seeded for this variant
                            v_existing = conn.execute(
                                "SELECT item_id FROM checklist_items WHERE service_id = ? AND document_name = ? AND variant_id = ?;",
                                (service_id, doc_name, vid)
                            ).fetchone()
                            if not v_existing:
                                conn.execute(
                                    """
                                    INSERT INTO checklist_items
                                        (service_id, variant_id, category_name, document_name, requirement_type,
                                         guidance_note, file_formats, format_instructions, display_order, is_active)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1);
                                    """,
                                    (service_id, vid, cat, doc_name, req_type, note, file_fmts, fmt_instr, order)
                                )
                            else:
                                conn.execute(
                                    "UPDATE checklist_items SET file_formats = ?, format_instructions = ? WHERE item_id = ?;",
                                    (file_fmts, fmt_instr, v_existing["item_id"])
                                )

            # 4. Seed Knowledge Documents & FTS
            for title, s_group, cat, content in KNOWLEDGE_BASE_ITEMS:
                existing_doc = conn.execute("SELECT doc_id FROM knowledge_documents WHERE title = ?;", (title,)).fetchone()
                if not existing_doc:
                    cur = conn.execute(
                        """
                        INSERT INTO knowledge_documents (title, service_group, category, content, created_at)
                        VALUES (?, ?, ?, ?, ?);
                        """,
                        (title, s_group, cat, content, now)
                    )
                    doc_id = cur.lastrowid
                    conn.execute(
                        "INSERT INTO knowledge_fts (rowid, title, service_group, content) VALUES (?, ?, ?, ?);",
                        (doc_id, title, s_group, content)
                    )

            # 5. Organization Profile baseline (blank by default)
            org_row = conn.execute("SELECT COUNT(*) FROM organisation_profile;").fetchone()
            if org_row[0] == 0:
                conn.execute(
                    """
                    INSERT INTO organisation_profile (firm_name, tagline, address, email, phone, website, created_at, updated_at)
                    VALUES ('', '', '', '', '', '', ?, ?);
                    """,
                    (now, now)
                )

            # 6. Default SMTP Configuration
            default_smtp = [
                ("smtp_host", "smtp.gmail.com"),
                ("smtp_port", "587"),
                ("smtp_user", ""),
                ("smtp_use_tls", "1"),
            ]
            for key, val in default_smtp:
                conn.execute(
                    "INSERT OR IGNORE INTO app_settings (setting_key, setting_value, updated_at) VALUES (?, ?, ?);",
                    (key, val, now)
                )
    finally:
        conn.close()
