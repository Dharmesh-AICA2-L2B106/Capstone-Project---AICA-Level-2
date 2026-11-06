"""SQLite database management, connection lifecycle, and schema initialization with strict integrity triggers."""

import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional
from src.clientdesk_ai.config.settings import CONFIG

SCHEMA_DDL = """
-- 1. Organisation Profile
CREATE TABLE IF NOT EXISTS organisation_profile (
    org_id INTEGER PRIMARY KEY AUTOINCREMENT,
    firm_name TEXT DEFAULT '',
    tagline TEXT DEFAULT '',
    address TEXT DEFAULT '',
    email TEXT DEFAULT '',
    phone TEXT DEFAULT '',
    website TEXT DEFAULT '',
    logo_path TEXT DEFAULT '',
    financial_year_start TEXT DEFAULT '04-01',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 2. Users
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    full_name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'STAFF' CHECK (role IN ('ADMIN', 'PARTNER', 'SENIOR', 'STAFF', 'READ_ONLY')),
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    last_login TEXT
);

-- 3. Roles and Permissions
CREATE TABLE IF NOT EXISTS roles (
    role_id INTEGER PRIMARY KEY AUTOINCREMENT,
    role_name TEXT UNIQUE NOT NULL,
    description TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS permissions (
    permission_id INTEGER PRIMARY KEY AUTOINCREMENT,
    permission_code TEXT UNIQUE NOT NULL,
    description TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS role_permissions (
    role_name TEXT NOT NULL,
    permission_code TEXT NOT NULL,
    PRIMARY KEY (role_name, permission_code)
);

-- 4. User Sessions
CREATE TABLE IF NOT EXISTS user_sessions (
    session_id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

-- 5. Login Attempts (for rate limiting / lockout)
CREATE TABLE IF NOT EXISTS login_attempts (
    attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    ip_address TEXT DEFAULT '127.0.0.1',
    attempt_time TEXT NOT NULL,
    is_successful INTEGER NOT NULL
);

-- 6. Clients
CREATE TABLE IF NOT EXISTS clients (
    client_id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_code TEXT UNIQUE NOT NULL,
    client_name TEXT NOT NULL,
    trade_name TEXT DEFAULT '',
    entity_type TEXT NOT NULL DEFAULT 'Sole Proprietorship',
    pan TEXT DEFAULT '',
    aadhaar TEXT DEFAULT '',
    gstin TEXT DEFAULT '',
    email TEXT DEFAULT '',
    phone TEXT DEFAULT '',
    address TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'INACTIVE', 'ARCHIVED')),
    created_by INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (created_by) REFERENCES users(user_id)
);

CREATE INDEX IF NOT EXISTS idx_clients_code ON clients(client_code);
CREATE INDEX IF NOT EXISTS idx_clients_name ON clients(client_name);

-- 7. Client Contacts
CREATE TABLE IF NOT EXISTS client_contacts (
    contact_id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL,
    contact_person TEXT NOT NULL,
    designation TEXT DEFAULT '',
    email TEXT DEFAULT '',
    phone TEXT DEFAULT '',
    is_primary INTEGER DEFAULT 1,
    FOREIGN KEY (client_id) REFERENCES clients(client_id)
);

-- 8. Service Templates
CREATE TABLE IF NOT EXISTS service_templates (
    service_id INTEGER PRIMARY KEY AUTOINCREMENT,
    service_code TEXT UNIQUE NOT NULL,
    service_name TEXT NOT NULL,
    service_group TEXT NOT NULL,
    description TEXT DEFAULT '',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

-- 9. Template Versions
CREATE TABLE IF NOT EXISTS template_versions (
    version_id INTEGER PRIMARY KEY AUTOINCREMENT,
    service_id INTEGER NOT NULL,
    version_number INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'APPROVED' CHECK (status IN ('DRAFT', 'UNDER_REVIEW', 'APPROVED', 'RETIRED')),
    effective_from TEXT NOT NULL,
    approved_by INTEGER,
    approved_at TEXT,
    FOREIGN KEY (service_id) REFERENCES service_templates(service_id)
);

-- 10. Template Variants (GST Entity Types locked to 8 approved variants)
CREATE TABLE IF NOT EXISTS template_variants (
    variant_id INTEGER PRIMARY KEY AUTOINCREMENT,
    service_id INTEGER NOT NULL,
    variant_code TEXT NOT NULL CHECK (variant_code IN (
        'SOLE_PROP', 'PARTNERSHIP', 'PVT_LTD', 'LLP',
        'HUF', 'TRUST', 'GOVT', 'CASUAL'
    )),
    variant_name TEXT NOT NULL,
    description TEXT DEFAULT '',
    is_active INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (service_id) REFERENCES service_templates(service_id),
    UNIQUE(service_id, variant_code)
);

-- 11. Checklist Categories
CREATE TABLE IF NOT EXISTS checklist_categories (
    category_id INTEGER PRIMARY KEY AUTOINCREMENT,
    service_id INTEGER NOT NULL,
    category_name TEXT NOT NULL,
    display_order INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (service_id) REFERENCES service_templates(service_id)
);

-- 12. Checklist Items
CREATE TABLE IF NOT EXISTS checklist_items (
    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    service_id INTEGER NOT NULL,
    variant_id INTEGER,
    category_name TEXT NOT NULL DEFAULT 'General Documents',
    document_name TEXT NOT NULL,
    requirement_type TEXT NOT NULL DEFAULT 'MANDATORY' CHECK (requirement_type IN ('MANDATORY', 'CONDITIONAL', 'OPTIONAL', 'REVIEW_REQUIRED')),
    condition_description TEXT DEFAULT '',
    guidance_note TEXT DEFAULT '',
    file_formats TEXT DEFAULT 'PDF, JPG',
    format_instructions TEXT DEFAULT '',
    display_order INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (service_id) REFERENCES service_templates(service_id),
    FOREIGN KEY (variant_id) REFERENCES template_variants(variant_id)
);

-- 13. Engagements (With Segregation of Duties Check)
CREATE TABLE IF NOT EXISTS engagements (
    engagement_id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL,
    service_id INTEGER NOT NULL,
    variant_id INTEGER,
    financial_year TEXT NOT NULL DEFAULT '2026-2027',
    tax_period TEXT NOT NULL DEFAULT 'Annual',
    due_date TEXT NOT NULL,
    priority TEXT NOT NULL DEFAULT 'NORMAL' CHECK (priority IN ('NORMAL', 'HIGH', 'URGENT')),
    status TEXT NOT NULL DEFAULT 'NOT_STARTED' CHECK (status IN (
        'NOT_STARTED', 'IN_PROGRESS', 'SUBMITTED_FOR_REVIEW', 'UNDER_REVIEW',
        'RETURNED_FOR_CORRECTION', 'APPROVED', 'COMPLETED', 'ON_HOLD', 'CANCELLED', 'REOPENED'
    )),
    assigned_to INTEGER,
    reviewer_id INTEGER,
    snapshot_sha256 TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    created_by INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (client_id) REFERENCES clients(client_id),
    FOREIGN KEY (service_id) REFERENCES service_templates(service_id),
    FOREIGN KEY (variant_id) REFERENCES template_variants(variant_id),
    FOREIGN KEY (assigned_to) REFERENCES users(user_id),
    FOREIGN KEY (reviewer_id) REFERENCES users(user_id),
    -- DB Level Segregation of Duties: Assigned Operator cannot be the Designated Reviewer
    CHECK (assigned_to IS NULL OR reviewer_id IS NULL OR assigned_to <> reviewer_id)
);

CREATE INDEX IF NOT EXISTS idx_engagements_client ON engagements(client_id);
CREATE INDEX IF NOT EXISTS idx_engagements_status ON engagements(status);
CREATE INDEX IF NOT EXISTS idx_engagements_assigned ON engagements(assigned_to);

-- 14. Engagement Checklist Items (Immutable snapshot at creation)
CREATE TABLE IF NOT EXISTS engagement_checklist_items (
    engagement_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    engagement_id INTEGER NOT NULL,
    source_item_id INTEGER,
    category_name TEXT NOT NULL,
    document_name_snapshot TEXT NOT NULL,
    requirement_snapshot TEXT NOT NULL CHECK (requirement_snapshot IN ('MANDATORY', 'CONDITIONAL', 'OPTIONAL', 'REVIEW_REQUIRED')),
    applicability_status TEXT NOT NULL DEFAULT 'APPLICABLE' CHECK (applicability_status IN ('UNDECIDED', 'APPLICABLE', 'NOT_APPLICABLE')),
    collection_status TEXT NOT NULL DEFAULT 'NOT_REQUESTED' CHECK (collection_status IN (
        'NOT_REQUESTED', 'REQUESTED', 'RECEIVED', 'UNDER_VERIFICATION',
        'ACCEPTED', 'DEFICIENT', 'NOT_APPLICABLE', 'WAIVED_WITH_APPROVAL'
    )),
    file_formats TEXT DEFAULT 'PDF, JPG',
    format_instructions TEXT DEFAULT '',
    received_date TEXT,
    verified_by INTEGER,
    waived_by INTEGER,
    waiver_reason TEXT DEFAULT '',
    deficiency_reason TEXT DEFAULT '',
    internal_remarks TEXT DEFAULT '',
    display_order INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (engagement_id) REFERENCES engagements(engagement_id),
    FOREIGN KEY (verified_by) REFERENCES users(user_id),
    FOREIGN KEY (waived_by) REFERENCES users(user_id)
);

CREATE INDEX IF NOT EXISTS idx_e_items_engagement ON engagement_checklist_items(engagement_id);

-- 15. Document Attachments
CREATE TABLE IF NOT EXISTS document_attachments (
    attachment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    engagement_item_id INTEGER NOT NULL,
    original_filename TEXT NOT NULL,
    stored_filename TEXT NOT NULL,
    storage_relative_path TEXT NOT NULL,
    file_size_bytes INTEGER NOT NULL,
    sha256_hash TEXT NOT NULL,
    uploaded_by INTEGER NOT NULL,
    uploaded_at TEXT NOT NULL,
    is_archived INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (engagement_item_id) REFERENCES engagement_checklist_items(engagement_item_id),
    FOREIGN KEY (uploaded_by) REFERENCES users(user_id),
    -- Prevent duplicate file upload to the exact same checklist item
    UNIQUE(engagement_item_id, sha256_hash)
);

CREATE INDEX IF NOT EXISTS idx_attachments_item ON document_attachments(engagement_item_id);
CREATE INDEX IF NOT EXISTS idx_attachments_hash ON document_attachments(sha256_hash);

-- 16. Engagement Assignment History
CREATE TABLE IF NOT EXISTS engagement_assignments (
    assignment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    engagement_id INTEGER NOT NULL,
    assigned_user_id INTEGER NOT NULL,
    assigned_role TEXT NOT NULL DEFAULT 'OPERATOR',
    assigned_by INTEGER NOT NULL,
    assigned_at TEXT NOT NULL,
    FOREIGN KEY (engagement_id) REFERENCES engagements(engagement_id),
    FOREIGN KEY (assigned_user_id) REFERENCES users(user_id)
);

-- 17. Follow-Up Logs
CREATE TABLE IF NOT EXISTS follow_up_logs (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    engagement_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    communication_mode TEXT NOT NULL DEFAULT 'Phone Call',
    summary_of_request TEXT NOT NULL,
    client_response TEXT DEFAULT '',
    next_follow_up_date TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (engagement_id) REFERENCES engagements(engagement_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

-- 18. Review Logs
CREATE TABLE IF NOT EXISTS review_logs (
    review_id INTEGER PRIMARY KEY AUTOINCREMENT,
    engagement_id INTEGER NOT NULL,
    reviewer_id INTEGER NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('APPROVED', 'RETURNED_FOR_CORRECTION', 'UNDER_REVIEW')),
    observations TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (engagement_id) REFERENCES engagements(engagement_id),
    FOREIGN KEY (reviewer_id) REFERENCES users(user_id)
);

-- 19. Engagement Status History
CREATE TABLE IF NOT EXISTS engagement_status_history (
    history_id INTEGER PRIMARY KEY AUTOINCREMENT,
    engagement_id INTEGER NOT NULL,
    old_status TEXT NOT NULL,
    new_status TEXT NOT NULL,
    changed_by INTEGER NOT NULL,
    reason TEXT DEFAULT '',
    changed_at TEXT NOT NULL,
    FOREIGN KEY (engagement_id) REFERENCES engagements(engagement_id),
    FOREIGN KEY (changed_by) REFERENCES users(user_id)
);

-- 20. Knowledge Documents & Passages (for local FTS5 search)
CREATE TABLE IF NOT EXISTS knowledge_documents (
    doc_id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    service_group TEXT NOT NULL,
    category TEXT DEFAULT 'SOP',
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- FTS5 Virtual Table for full-text offline search
CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(
    title,
    service_group,
    content,
    content='knowledge_documents',
    content_rowid='doc_id'
);

-- 21. App Settings
CREATE TABLE IF NOT EXISTS app_settings (
    setting_key TEXT PRIMARY KEY,
    setting_value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 22. Audit Logs
CREATE TABLE IF NOT EXISTS audit_logs (
    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER,
    actor_username TEXT DEFAULT '',
    event_type TEXT NOT NULL,
    target_entity TEXT NOT NULL,
    target_id TEXT DEFAULT '',
    details TEXT DEFAULT '',
    timestamp TEXT NOT NULL
);

-- 23. Backup Logs
CREATE TABLE IF NOT EXISTS backup_logs (
    backup_id INTEGER PRIMARY KEY AUTOINCREMENT,
    backup_type TEXT NOT NULL DEFAULT 'MANUAL',
    archive_path TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    item_count INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'SUCCESS',
    details TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

-- =====================================================================
-- DATABASE INTEGRITY TRIGGERS (ARCHITECTURAL CONTROLS)
-- =====================================================================

-- Trigger B: Immutability of Checklist Snapshot Wording & Requirement Type
CREATE TRIGGER IF NOT EXISTS trg_prevent_snapshot_item_tampering
BEFORE UPDATE OF document_name_snapshot, requirement_snapshot, source_item_id ON engagement_checklist_items
WHEN OLD.document_name_snapshot <> NEW.document_name_snapshot OR OLD.requirement_snapshot <> NEW.requirement_snapshot
BEGIN
    SELECT RAISE(ABORT, 'Snapshot Immutability Violation: document_name_snapshot and requirement_snapshot are tamper-proof and cannot be altered.');
END;

-- Trigger C: Prevent Deleting Checklist Snapshot Items
CREATE TRIGGER IF NOT EXISTS trg_prevent_snapshot_item_deletion
BEFORE DELETE ON engagement_checklist_items
BEGIN
    SELECT RAISE(ABORT, 'Snapshot Immutability Violation: Engagement checklist snapshot items cannot be deleted once created.');
END;

-- Trigger D: Segregation of Duties on Review Log Insert
CREATE TRIGGER IF NOT EXISTS trg_enforce_segregation_on_review
BEFORE INSERT ON review_logs
BEGIN
    -- 1. Reviewer cannot be the assigned operator
    SELECT CASE
        WHEN NEW.reviewer_id = (SELECT assigned_to FROM engagements WHERE engagement_id = NEW.engagement_id)
        THEN RAISE(ABORT, 'Segregation of Duties Violation: Assigned operator cannot review or approve their own engagement.')
    END;
    -- 2. Reviewer must have a supervisory role
    SELECT CASE
        WHEN (SELECT role FROM users WHERE user_id = NEW.reviewer_id) NOT IN ('ADMIN', 'PARTNER', 'SENIOR')
        THEN RAISE(ABORT, 'Authorization Violation: Only Admin, Partner, or Senior users can record review approvals.')
    END;
END;

-- Trigger E: Statutory Readiness Gate on Engagement Status Change
CREATE TRIGGER IF NOT EXISTS trg_enforce_readiness_on_status_change
BEFORE UPDATE OF status ON engagements
WHEN NEW.status IN ('SUBMITTED_FOR_REVIEW', 'APPROVED', 'COMPLETED')
BEGIN
    -- Check 1: Mandatory applicable documents must be accepted or waived
    SELECT CASE
        WHEN EXISTS (
            SELECT 1 FROM engagement_checklist_items
            WHERE engagement_id = NEW.engagement_id
              AND requirement_snapshot = 'MANDATORY'
              AND applicability_status = 'APPLICABLE'
              AND collection_status NOT IN ('ACCEPTED', 'WAIVED_WITH_APPROVAL')
        )
        THEN RAISE(ABORT, 'Readiness Gate Blocked: All applicable mandatory documents must be accepted or waived.')
    END;

    -- Check 2: Unresolved deficiencies must block submission/approval
    SELECT CASE
        WHEN EXISTS (
            SELECT 1 FROM engagement_checklist_items
            WHERE engagement_id = NEW.engagement_id
              AND collection_status = 'DEFICIENT'
        )
        THEN RAISE(ABORT, 'Readiness Gate Blocked: Unresolved document deficiencies exist.')
    END;
END;

-- Trigger F: Automatic FTS5 Index Synchronization on Knowledge Documents
CREATE TRIGGER IF NOT EXISTS trg_knowledge_ai
AFTER INSERT ON knowledge_documents
BEGIN
    INSERT INTO knowledge_fts (rowid, title, service_group, content)
    VALUES (NEW.doc_id, NEW.title, NEW.service_group, NEW.content);
END;

CREATE TRIGGER IF NOT EXISTS trg_knowledge_ad
AFTER DELETE ON knowledge_documents
BEGIN
    INSERT INTO knowledge_fts (knowledge_fts, rowid, title, service_group, content)
    VALUES ('delete', OLD.doc_id, OLD.title, OLD.service_group, OLD.content);
END;

CREATE TRIGGER IF NOT EXISTS trg_knowledge_au
AFTER UPDATE ON knowledge_documents
BEGIN
    INSERT INTO knowledge_fts (knowledge_fts, rowid, title, service_group, content)
    VALUES ('delete', OLD.doc_id, OLD.title, OLD.service_group, OLD.content);
    INSERT INTO knowledge_fts (rowid, title, service_group, content)
    VALUES (NEW.doc_id, NEW.title, NEW.service_group, NEW.content);
END;
"""


def get_db_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Open a SQLite connection configured with WAL mode, foreign keys, and dictionary rows."""
    path = db_path or CONFIG.db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


def init_database(db_path: Optional[Path] = None) -> None:
    """Execute DDL statements, trigger setup, and state reconciliation."""
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.executescript(SCHEMA_DDL)

            # ── Migration: Remove scope lock trigger and hardcoded CHECK constraints ──
            conn.execute("DROP TRIGGER IF EXISTS trg_prevent_unapproved_service_count;")
            tbl_sql_row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='service_templates';").fetchone()
            if tbl_sql_row and tbl_sql_row[0] and "CHECK (service_code IN" in tbl_sql_row[0]:
                conn.execute("PRAGMA foreign_keys = OFF;")
                conn.execute("ALTER TABLE service_templates RENAME TO service_templates_old;")
                conn.execute("""
                    CREATE TABLE service_templates (
                        service_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        service_code TEXT UNIQUE NOT NULL,
                        service_name TEXT NOT NULL,
                        service_group TEXT NOT NULL,
                        description TEXT DEFAULT '',
                        is_active INTEGER NOT NULL DEFAULT 1,
                        created_at TEXT NOT NULL
                    );
                """)
                conn.execute("""
                    INSERT INTO service_templates (service_id, service_code, service_name, service_group, description, is_active, created_at)
                    SELECT service_id, service_code, service_name, service_group, description, is_active, created_at FROM service_templates_old;
                """)
                conn.execute("DROP TABLE service_templates_old;")
                conn.execute("PRAGMA foreign_keys = ON;")

            # ── Migration: add aadhaar to clients ──
            _ccols = {r[1] for r in conn.execute("PRAGMA table_info(clients);").fetchall()}
            if "aadhaar" not in _ccols:
                conn.execute("ALTER TABLE clients ADD COLUMN aadhaar TEXT DEFAULT '';")

            # ── Migration: add file_formats / format_instructions to checklist_items ──
            _cols = {r[1] for r in conn.execute("PRAGMA table_info(checklist_items);").fetchall()}
            if "file_formats" not in _cols:
                conn.execute("ALTER TABLE checklist_items ADD COLUMN file_formats TEXT DEFAULT 'PDF, JPG';")
            if "format_instructions" not in _cols:
                conn.execute("ALTER TABLE checklist_items ADD COLUMN format_instructions TEXT DEFAULT '';")

            # ── Migration: add file_formats / format_instructions to engagement_checklist_items ──
            _ecols = {r[1] for r in conn.execute("PRAGMA table_info(engagement_checklist_items);").fetchall()}
            if "file_formats" not in _ecols:
                conn.execute("ALTER TABLE engagement_checklist_items ADD COLUMN file_formats TEXT DEFAULT 'PDF, JPG';")
            if "format_instructions" not in _ecols:
                conn.execute("ALTER TABLE engagement_checklist_items ADD COLUMN format_instructions TEXT DEFAULT '';")

            # ── Migration: default SMTP app_settings ──
            now_iso = datetime.now(timezone.utc).isoformat()
            default_smtp = [
                ("smtp_host", "smtp.gmail.com"),
                ("smtp_port", "587"),
                ("smtp_user", ""),
                ("smtp_use_tls", "1"),
            ]
            for key, val in default_smtp:
                conn.execute(
                    "INSERT OR IGNORE INTO app_settings (setting_key, setting_value, updated_at) VALUES (?, ?, ?);",
                    (key, val, now_iso)
                )

            # ── Migration: default 14-day evaluation trial settings ──
            trial_start = conn.execute("SELECT setting_value FROM app_settings WHERE setting_key = 'trial_start_date';").fetchone()
            if not trial_start:
                today_str = datetime.now(timezone.utc).date().isoformat()
                expiry_str = (datetime.now(timezone.utc).date() + timedelta(days=14)).isoformat()
                conn.execute(
                    "INSERT OR IGNORE INTO app_settings (setting_key, setting_value, updated_at) VALUES ('trial_start_date', ?, ?);",
                    (today_str, now_iso)
                )
                conn.execute(
                    "INSERT OR IGNORE INTO app_settings (setting_key, setting_value, updated_at) VALUES ('trial_expiry_date', ?, ?);",
                    (expiry_str, now_iso)
                )
                conn.execute(
                    "INSERT OR IGNORE INTO app_settings (setting_key, setting_value, updated_at) VALUES ('license_status', 'TRIAL', ?);",
                    (now_iso,)
                )
                conn.execute(
                    "INSERT OR IGNORE INTO app_settings (setting_key, setting_value, updated_at) VALUES ('license_last_run_date', ?, ?);",
                    (today_str, now_iso)
                )

            # Reconcile inconsistent applicability / collection statuses
            conn.execute(
                "UPDATE engagement_checklist_items SET collection_status = 'NOT_APPLICABLE' WHERE applicability_status = 'NOT_APPLICABLE' AND collection_status != 'NOT_APPLICABLE';"
            )
            conn.execute(
                "UPDATE engagement_checklist_items SET applicability_status = 'NOT_APPLICABLE' WHERE collection_status = 'NOT_APPLICABLE' AND applicability_status != 'NOT_APPLICABLE';"
            )

            # Ensure master admin password is set to 'admin'
            try:
                from src.clientdesk_ai.security.crypto import hash_password
                admin_hash = hash_password("admin")
                conn.execute("UPDATE users SET password_hash = ? WHERE username = 'admin';", (admin_hash,))
            except Exception:
                pass

            # Ensure master SOP Wiki article is seeded
            wiki_exists = conn.execute("SELECT doc_id FROM knowledge_documents WHERE title = 'Firm SOP Wiki & Compliance Knowledge Base';").fetchone()
            if not wiki_exists:
                conn.execute(
                    """
                    INSERT INTO knowledge_documents (title, service_group, category, content, created_at)
                    VALUES (?, ?, ?, ?, ?);
                    """,
                    (
                        "Firm SOP Wiki & Compliance Knowledge Base",
                        "General Compliance",
                        "SOP",
                        "Welcome to the Firm Wiki & SOP Knowledge Base. This centralized repository contains official standard operating procedures (SOP), statutory filing rules, compliance checklists, documentation standards, and verification guidelines for statutory disciplines including GST, Income Tax (ITR), Company Formation, MCA Annual Compliance, LLP, and Audits. All staff, seniors, and partners must adhere to these firm guidelines.",
                        now_iso
                    )
                )
                try:
                    conn.execute("INSERT INTO knowledge_fts(knowledge_fts) VALUES('rebuild');")
                except Exception:
                    pass
    finally:
        conn.close()
