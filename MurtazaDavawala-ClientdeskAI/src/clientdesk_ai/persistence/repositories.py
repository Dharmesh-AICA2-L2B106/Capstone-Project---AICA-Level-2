"""Typed data access repositories for clients, templates, engagements, attachments, and logs."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
import sqlite3

from src.clientdesk_ai.domain.models import (
    User, UserRole, Client, ServiceTemplate, TemplateVariant, ChecklistItem,
    Engagement, EngagementChecklistItem, DocumentAttachment, FollowUpLog,
    ReviewLog, AuditLog, ReadinessSummary, RequirementType, DocumentStatus,
    ApplicabilityStatus, Priority, EngagementStatus
)
from src.clientdesk_ai.persistence.database import get_db_connection


class UserRepository:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path

    def get_by_username(self, username: str) -> Optional[User]:
        conn = get_db_connection(self.db_path)
        try:
            row = conn.execute("SELECT * FROM users WHERE username = ?;", (username,)).fetchone()
            if not row:
                return None
            return User(
                user_id=row["user_id"],
                username=row["username"],
                full_name=row["full_name"],
                email=row["email"],
                password_hash=row["password_hash"],
                role=UserRole(row["role"]),
                is_active=bool(row["is_active"]),
                created_at=row["created_at"],
                last_login=row["last_login"]
            )
        finally:
            conn.close()

    def get_by_id(self, user_id: int) -> Optional[User]:
        conn = get_db_connection(self.db_path)
        try:
            row = conn.execute("SELECT * FROM users WHERE user_id = ?;", (user_id,)).fetchone()
            if not row:
                return None
            return User(
                user_id=row["user_id"],
                username=row["username"],
                full_name=row["full_name"],
                email=row["email"],
                password_hash=row["password_hash"],
                role=UserRole(row["role"]),
                is_active=bool(row["is_active"]),
                created_at=row["created_at"],
                last_login=row["last_login"]
            )
        finally:
            conn.close()

    def list_all(self) -> List[User]:
        conn = get_db_connection(self.db_path)
        try:
            rows = conn.execute("SELECT * FROM users ORDER BY full_name ASC;").fetchall()
            return [
                User(
                    user_id=r["user_id"],
                    username=r["username"],
                    full_name=r["full_name"],
                    email=r["email"],
                    password_hash=r["password_hash"],
                    role=UserRole(r["role"]),
                    is_active=bool(r["is_active"]),
                    created_at=r["created_at"],
                    last_login=r["last_login"]
                ) for r in rows
            ]
        finally:
            conn.close()

    def create_user(self, user: User) -> int:
        conn = get_db_connection(self.db_path)
        now = datetime.now(timezone.utc).isoformat()
        try:
            with conn:
                cur = conn.execute(
                    """
                    INSERT INTO users (username, full_name, email, password_hash, role, is_active, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?);
                    """,
                    (user.username, user.full_name, user.email, user.password_hash, user.role.value, 1 if user.is_active else 0, now)
                )
                return cur.lastrowid
        finally:
            conn.close()

    def record_login_attempt(self, username: str, is_successful: bool) -> None:
        conn = get_db_connection(self.db_path)
        now = datetime.now(timezone.utc).isoformat()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO login_attempts (username, attempt_time, is_successful) VALUES (?, ?, ?);",
                    (username, now, 1 if is_successful else 0)
                )
        finally:
            conn.close()

    def count_recent_failed_attempts(self, username: str) -> int:
        conn = get_db_connection(self.db_path)
        try:
            row = conn.execute(
                """
                SELECT COUNT(*) FROM login_attempts
                WHERE username = ? AND is_successful = 0
                AND attempt_time >= datetime('now', '-15 minutes');
                """,
                (username,)
            ).fetchone()
            return row[0] if row else 0
        finally:
            conn.close()

    def update_password(self, user_id: int, new_password_hash: str) -> bool:
        """Update a user's password hash. Assigned and managed strictly by Administrator."""
        conn = get_db_connection(self.db_path)
        try:
            with conn:
                conn.execute(
                    "UPDATE users SET password_hash = ? WHERE user_id = ?;",
                    (new_password_hash, user_id)
                )
            return True
        finally:
            conn.close()

    def delete_user(self, user_id: int) -> Tuple[bool, str]:
        """Delete or deactivate user. If user has existing filings, mark inactive to preserve audit trail."""
        conn = get_db_connection(self.db_path)
        try:
            with conn:
                # Check if user has active engagements or review logs
                cur = conn.execute("SELECT COUNT(*) FROM engagements WHERE assigned_to = ? OR reviewer_id = ?;", (user_id, user_id))
                has_engagements = cur.fetchone()[0] > 0
                if has_engagements:
                    conn.execute("UPDATE users SET is_active = 0 WHERE user_id = ?;", (user_id,))
                    return True, "User has existing engagement records. Account deactivated to preserve audit history."
                conn.execute("DELETE FROM users WHERE user_id = ?;", (user_id,))
                return True, "User account successfully deleted."
        except Exception as e:
            return False, f"Failed to remove user: {e}"
        finally:
            conn.close()

    def update_role(self, user_id: int, new_role: UserRole) -> bool:
        """Update role authority of a user."""
        conn = get_db_connection(self.db_path)
        try:
            with conn:
                conn.execute(
                    "UPDATE users SET role = ? WHERE user_id = ?;",
                    (new_role.value if hasattr(new_role, "value") else str(new_role), user_id)
                )
            return True
        finally:
            conn.close()


class ClientRepository:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path

    def create(self, client: Client) -> int:
        conn = get_db_connection(self.db_path)
        now = datetime.now(timezone.utc).isoformat()
        try:
            with conn:
                cols = {r[1] for r in conn.execute("PRAGMA table_info(clients);").fetchall()}
                if "aadhaar" in cols:
                    cur = conn.execute(
                        """
                        INSERT INTO clients (client_code, client_name, trade_name, entity_type, pan, aadhaar, gstin, email, phone, address, status, created_by, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                        """,
                        (client.client_code.strip().upper(), client.client_name.strip(), client.trade_name.strip(),
                         client.entity_type, client.pan.strip().upper(), getattr(client, "aadhaar", "").strip(), client.gstin.strip().upper(),
                         client.email.strip(), client.phone.strip(), client.address.strip(),
                         client.status, client.created_by, now, now)
                    )
                else:
                    cur = conn.execute(
                        """
                        INSERT INTO clients (client_code, client_name, trade_name, entity_type, pan, gstin, email, phone, address, status, created_by, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                        """,
                        (client.client_code.strip().upper(), client.client_name.strip(), client.trade_name.strip(),
                         client.entity_type, client.pan.strip().upper(), client.gstin.strip().upper(),
                         client.email.strip(), client.phone.strip(), client.address.strip(),
                         client.status, client.created_by, now, now)
                    )
                return cur.lastrowid
        finally:
            conn.close()

    def update(self, client: Client) -> None:
        conn = get_db_connection(self.db_path)
        now = datetime.now(timezone.utc).isoformat()
        try:
            with conn:
                cols = {r[1] for r in conn.execute("PRAGMA table_info(clients);").fetchall()}
                if "aadhaar" in cols:
                    conn.execute(
                        """
                        UPDATE clients SET client_name = ?, trade_name = ?, entity_type = ?, pan = ?, aadhaar = ?, gstin = ?,
                                           email = ?, phone = ?, address = ?, status = ?, updated_at = ?
                        WHERE client_id = ?;
                        """,
                        (client.client_name, client.trade_name, client.entity_type, client.pan, getattr(client, "aadhaar", "").strip(), client.gstin,
                         client.email, client.phone, client.address, client.status, now, client.client_id)
                    )
                else:
                    conn.execute(
                        """
                        UPDATE clients SET client_name = ?, trade_name = ?, entity_type = ?, pan = ?, gstin = ?,
                                           email = ?, phone = ?, address = ?, status = ?, updated_at = ?
                        WHERE client_id = ?;
                        """,
                        (client.client_name, client.trade_name, client.entity_type, client.pan, client.gstin,
                         client.email, client.phone, client.address, client.status, now, client.client_id)
                    )
        finally:
            conn.close()

    def delete(self, client_id: int) -> Tuple[bool, str]:
        conn = get_db_connection(self.db_path)
        try:
            with conn:
                eng_count = conn.execute("SELECT COUNT(*) FROM engagements WHERE client_id = ?;", (client_id,)).fetchone()[0]
                if eng_count > 0:
                    conn.execute("UPDATE clients SET status = 'INACTIVE' WHERE client_id = ?;", (client_id,))
                    return True, f"Client has {eng_count} engagement(s). Status set to INACTIVE to preserve audit trail."
                else:
                    conn.execute("DELETE FROM clients WHERE client_id = ?;", (client_id,))
                    return True, "Client removed successfully from master records."
        finally:
            conn.close()

    def get_by_id(self, client_id: int) -> Optional[Client]:
        conn = get_db_connection(self.db_path)
        try:
            row = conn.execute("SELECT * FROM clients WHERE client_id = ?;", (client_id,)).fetchone()
            if not row:
                return None
            return self._row_to_client(row)
        finally:
            conn.close()

    def get_by_code(self, client_code: str) -> Optional[Client]:
        conn = get_db_connection(self.db_path)
        try:
            row = conn.execute("SELECT * FROM clients WHERE client_code = ?;", (client_code.strip().upper(),)).fetchone()
            if not row:
                return None
            return self._row_to_client(row)
        finally:
            conn.close()

    def search(self, query: str = "") -> List[Client]:
        conn = get_db_connection(self.db_path)
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(clients);").fetchall()}
            if not query.strip():
                rows = conn.execute("SELECT * FROM clients ORDER BY client_name ASC;").fetchall()
            else:
                q = f"%{query.strip()}%"
                if "aadhaar" in cols:
                    rows = conn.execute(
                        """
                        SELECT * FROM clients
                        WHERE client_code LIKE ? OR client_name LIKE ? OR trade_name LIKE ? OR pan LIKE ? OR aadhaar LIKE ? OR gstin LIKE ?
                        ORDER BY client_name ASC;
                        """,
                        (q, q, q, q, q, q)
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """
                        SELECT * FROM clients
                        WHERE client_code LIKE ? OR client_name LIKE ? OR trade_name LIKE ? OR pan LIKE ? OR gstin LIKE ?
                        ORDER BY client_name ASC;
                        """,
                        (q, q, q, q, q)
                    ).fetchall()
            return [self._row_to_client(r) for r in rows]
        finally:
            conn.close()

    def generate_next_client_code(self) -> str:
        """Scan existing client records and compute the next sequential client code (e.g. CLT-0001, CLT-0002)."""
        conn = get_db_connection(self.db_path)
        try:
            rows = conn.execute("SELECT client_code FROM clients;").fetchall()
            max_num = 0
            for r in rows:
                code = (r[0] or "").strip().upper()
                if code.startswith("CLT-"):
                    num_part = code[4:]
                    if num_part.isdigit():
                        max_num = max(max_num, int(num_part))
                elif code.isdigit():
                    max_num = max(max_num, int(code))
            if max_num == 0:
                count = conn.execute("SELECT COUNT(*) FROM clients;").fetchone()[0]
                max_num = count
            return f"CLT-{max_num + 1:04d}"
        finally:
            conn.close()

    def _row_to_client(self, row: sqlite3.Row) -> Client:
        keys = row.keys()
        return Client(
            client_id=row["client_id"],
            client_code=row["client_code"],
            client_name=row["client_name"],
            trade_name=row["trade_name"] or "",
            entity_type=row["entity_type"] or "Sole Proprietorship",
            pan=row["pan"] or "",
            aadhaar=row["aadhaar"] if "aadhaar" in keys and row["aadhaar"] else "",
            gstin=row["gstin"] or "",
            email=row["email"] or "",
            phone=row["phone"] or "",
            address=row["address"] or "",
            status=row["status"] or "ACTIVE",
            created_by=row["created_by"] or 1,
            created_at=row["created_at"] or "",
            updated_at=row["updated_at"] or ""
        )


class TemplateRepository:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path

    def list_services(self) -> List[ServiceTemplate]:
        conn = get_db_connection(self.db_path)
        try:
            rows = conn.execute("SELECT * FROM service_templates WHERE is_active = 1 ORDER BY service_group, service_name;").fetchall()
            return [
                ServiceTemplate(
                    service_id=r["service_id"],
                    service_code=r["service_code"],
                    service_name=r["service_name"],
                    service_group=r["service_group"],
                    description=r["description"] or "",
                    is_active=bool(r["is_active"]),
                    created_at=r["created_at"] or ""
                ) for r in rows
            ]
        finally:
            conn.close()

    def list_service_groups(self) -> List[str]:
        conn = get_db_connection(self.db_path)
        try:
            rows = conn.execute(
                "SELECT DISTINCT service_group FROM service_templates WHERE is_active = 1 ORDER BY service_group;"
            ).fetchall()
            return [r[0] for r in rows if r[0]]
        finally:
            conn.close()

    def create_service(self, service_code: str, service_name: str, service_group: str, description: str = "") -> int:
        conn = get_db_connection(self.db_path)
        now = datetime.now(timezone.utc).isoformat()
        try:
            with conn:
                cur = conn.execute(
                    """
                    INSERT INTO service_templates (service_code, service_name, service_group, description, is_active, created_at)
                    VALUES (?, ?, ?, ?, 1, ?);
                    """,
                    (service_code.strip().upper(), service_name.strip(), service_group.strip(), description.strip(), now)
                )
                return cur.lastrowid
        finally:
            conn.close()

    def get_service(self, service_id: int) -> Optional[ServiceTemplate]:
        conn = get_db_connection(self.db_path)
        try:
            r = conn.execute("SELECT * FROM service_templates WHERE service_id = ?;", (service_id,)).fetchone()
            if not r:
                return None
            return ServiceTemplate(
                service_id=r["service_id"],
                service_code=r["service_code"],
                service_name=r["service_name"],
                service_group=r["service_group"],
                description=r["description"] or "",
                is_active=bool(r["is_active"]),
                created_at=r["created_at"] or ""
            )
        finally:
            conn.close()

    def list_variants(self, service_id: int) -> List[TemplateVariant]:
        conn = get_db_connection(self.db_path)
        try:
            rows = conn.execute("SELECT * FROM template_variants WHERE service_id = ? AND is_active = 1 ORDER BY variant_id;", (service_id,)).fetchall()
            return [
                TemplateVariant(
                    variant_id=r["variant_id"],
                    service_id=r["service_id"],
                    variant_code=r["variant_code"],
                    variant_name=r["variant_name"],
                    description=r["description"] or "",
                    is_active=bool(r["is_active"])
                ) for r in rows
            ]
        finally:
            conn.close()

    def get_items(self, service_id: int, variant_id: Optional[int] = None, all_variants: bool = False) -> List[ChecklistItem]:
        conn = get_db_connection(self.db_path)
        try:
            if all_variants:
                rows = conn.execute(
                    """
                    SELECT * FROM checklist_items
                    WHERE service_id = ? AND is_active = 1
                    ORDER BY display_order ASC, item_id ASC;
                    """,
                    (service_id,)
                ).fetchall()
            else:
                # Include universal items (variant_id IS NULL) plus items specific to this variant
                rows = conn.execute(
                    """
                    SELECT * FROM checklist_items
                    WHERE service_id = ? AND is_active = 1
                      AND (variant_id IS NULL OR variant_id = ?)
                    ORDER BY display_order ASC, item_id ASC;
                    """,
                    (service_id, variant_id)
                ).fetchall()
            return [
                ChecklistItem(
                    item_id=r["item_id"],
                    service_id=r["service_id"],
                    variant_id=r["variant_id"],
                    category_name=r["category_name"] or "General Documents",
                    document_name=r["document_name"],
                    requirement_type=RequirementType(r["requirement_type"]),
                    condition_description=r["condition_description"] or "",
                    guidance_note=r["guidance_note"] or "",
                    file_formats=r["file_formats"] if "file_formats" in r.keys() else "PDF, JPG",
                    format_instructions=r["format_instructions"] if "format_instructions" in r.keys() else "",
                    display_order=r["display_order"] or 0,
                    is_active=bool(r["is_active"])
                ) for r in rows
            ]
        finally:
            conn.close()

    def get_item(self, item_id: int) -> Optional[ChecklistItem]:
        conn = get_db_connection(self.db_path)
        try:
            r = conn.execute("SELECT * FROM checklist_items WHERE item_id = ?;", (item_id,)).fetchone()
            if not r:
                return None
            return ChecklistItem(
                item_id=r["item_id"],
                service_id=r["service_id"],
                variant_id=r["variant_id"],
                category_name=r["category_name"] or "General Documents",
                document_name=r["document_name"],
                requirement_type=RequirementType(r["requirement_type"]),
                condition_description=r["condition_description"] or "",
                guidance_note=r["guidance_note"] or "",
                file_formats=r["file_formats"] if "file_formats" in r.keys() else "PDF, JPG",
                format_instructions=r["format_instructions"] if "format_instructions" in r.keys() else "",
                display_order=r["display_order"] or 0,
                is_active=bool(r["is_active"])
            )
        finally:
            conn.close()

    def add_item(
        self,
        service_id: int,
        category_name: str,
        document_name: str,
        requirement_type: RequirementType,
        guidance_note: str = "",
        variant_id: Optional[int] = None,
        file_formats: str = "PDF, JPG",
        format_instructions: str = ""
    ) -> int:
        conn = get_db_connection(self.db_path)
        try:
            with conn:
                cur = conn.execute(
                    """
                    INSERT INTO checklist_items (
                        service_id, variant_id, category_name, document_name, requirement_type,
                        guidance_note, file_formats, format_instructions, display_order, is_active
                    ) VALUES (
                        ?, ?, ?, ?, ?,
                        ?, ?, ?, (SELECT COALESCE(MAX(display_order), 0) + 1 FROM checklist_items WHERE service_id = ?), 1
                    );
                    """,
                    (
                        service_id, variant_id, category_name.strip() or "General Documents",
                        document_name.strip(), requirement_type.value, guidance_note.strip(),
                        file_formats.strip() or "PDF, JPG", format_instructions.strip(), service_id
                    )
                )
                return cur.lastrowid
        finally:
            conn.close()

    def update_item(
        self,
        item_id: int,
        category_name: str,
        document_name: str,
        requirement_type: RequirementType,
        guidance_note: str = "",
        variant_id: Optional[int] = None,
        file_formats: str = "PDF, JPG",
        format_instructions: str = ""
    ) -> None:
        conn = get_db_connection(self.db_path)
        try:
            with conn:
                conn.execute(
                    """
                    UPDATE checklist_items
                    SET category_name = ?, document_name = ?, requirement_type = ?,
                        guidance_note = ?, variant_id = ?, file_formats = ?, format_instructions = ?
                    WHERE item_id = ?;
                    """,
                    (
                        category_name.strip() or "General Documents", document_name.strip(),
                        requirement_type.value, guidance_note.strip(), variant_id,
                        file_formats.strip() or "PDF, JPG", format_instructions.strip(), item_id
                    )
                )
        finally:
            conn.close()

    def delete_item(self, item_id: int) -> None:
        conn = get_db_connection(self.db_path)
        try:
            with conn:
                conn.execute("DELETE FROM checklist_items WHERE item_id = ?;", (item_id,))
        finally:
            conn.close()


class EngagementRepository:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path

    def create(self, engagement: Engagement) -> int:
        """Create an engagement and generate an immutable snapshot of template items in a transaction."""
        conn = get_db_connection(self.db_path)
        now = datetime.now(timezone.utc).isoformat()
        try:
            with conn:
                assigned_id = engagement.assigned_to if engagement.assigned_to and engagement.assigned_to > 0 else None
                reviewer_id = engagement.reviewer_id if engagement.reviewer_id and engagement.reviewer_id > 0 else None
                cur = conn.execute(
                    """
                    INSERT INTO engagements (client_id, service_id, variant_id, financial_year, tax_period, due_date, priority, status, assigned_to, reviewer_id, notes, created_by, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (engagement.client_id, engagement.service_id, engagement.variant_id, engagement.financial_year,
                     engagement.tax_period, engagement.due_date, engagement.priority.value, engagement.status.value,
                     assigned_id, reviewer_id, engagement.notes, engagement.created_by, now, now)
                )
                engagement_id = cur.lastrowid

                # Snapshot template checklist items — filter by variant:
                # Include universal items (variant_id IS NULL) PLUS items specific to the engagement's variant
                if engagement.variant_id:
                    items_cursor = conn.execute(
                        """
                        SELECT * FROM checklist_items
                        WHERE service_id = ? AND is_active = 1
                          AND (variant_id IS NULL OR variant_id = ?)
                        ORDER BY display_order ASC, item_id ASC;
                        """,
                        (engagement.service_id, engagement.variant_id)
                    )
                else:
                    items_cursor = conn.execute(
                        """
                        SELECT * FROM checklist_items
                        WHERE service_id = ? AND is_active = 1
                          AND variant_id IS NULL
                        ORDER BY display_order ASC, item_id ASC;
                        """,
                        (engagement.service_id,)
                    )
                template_items = items_cursor.fetchall()

                for itm in template_items:
                    # Carry file_formats and format_instructions if columns exist on template
                    col_keys = itm.keys() if hasattr(itm, 'keys') else []
                    fmt = itm["file_formats"] if "file_formats" in col_keys else "PDF, JPG"
                    fmt_instr = itm["format_instructions"] if "format_instructions" in col_keys else ""
                    conn.execute(
                        """
                        INSERT INTO engagement_checklist_items (
                            engagement_id, source_item_id, category_name, document_name_snapshot,
                            requirement_snapshot, applicability_status, collection_status,
                            file_formats, format_instructions, display_order
                        ) VALUES (?, ?, ?, ?, ?, 'APPLICABLE', 'NOT_REQUESTED', ?, ?, ?);
                        """,
                        (engagement_id, itm["item_id"], itm["category_name"], itm["document_name"],
                         itm["requirement_type"], fmt, fmt_instr, itm["display_order"])
                    )

                # Record status history
                conn.execute(
                    """
                    INSERT INTO engagement_status_history (engagement_id, old_status, new_status, changed_by, reason, changed_at)
                    VALUES (?, 'NONE', ?, ?, 'Engagement created with snapshot', ?);
                    """,
                    (engagement_id, engagement.status.value, engagement.created_by, now)
                )

                return engagement_id
        finally:
            conn.close()

    def get_by_id(self, engagement_id: int) -> Optional[Engagement]:
        conn = get_db_connection(self.db_path)
        try:
            row = conn.execute(
                """
                SELECT e.*, c.client_name, s.service_name, u_assigned.full_name as assigned_name, u_reviewer.full_name as reviewer_name
                FROM engagements e
                JOIN clients c ON e.client_id = c.client_id
                JOIN service_templates s ON e.service_id = s.service_id
                LEFT JOIN users u_assigned ON e.assigned_to = u_assigned.user_id
                LEFT JOIN users u_reviewer ON e.reviewer_id = u_reviewer.user_id
                WHERE e.engagement_id = ?;
                """,
                (engagement_id,)
            ).fetchone()
            if not row:
                return None
            return self._row_to_engagement(row)
        finally:
            conn.close()

    def list_all(self, client_id: Optional[int] = None, assigned_to: Optional[int] = None, status: Optional[str] = None) -> List[Engagement]:
        conn = get_db_connection(self.db_path)
        try:
            query = """
                SELECT e.*, c.client_name, s.service_name, u_assigned.full_name as assigned_name, u_reviewer.full_name as reviewer_name
                FROM engagements e
                JOIN clients c ON e.client_id = c.client_id
                JOIN service_templates s ON e.service_id = s.service_id
                LEFT JOIN users u_assigned ON e.assigned_to = u_assigned.user_id
                LEFT JOIN users u_reviewer ON e.reviewer_id = u_reviewer.user_id
                WHERE 1=1
            """
            params = []
            if client_id:
                query += " AND e.client_id = ?"
                params.append(client_id)
            if assigned_to:
                query += " AND e.assigned_to = ?"
                params.append(assigned_to)
            if status:
                query += " AND e.status = ?"
                params.append(status)
            query += " ORDER BY e.due_date ASC, e.engagement_id DESC;"

            rows = conn.execute(query, tuple(params)).fetchall()
            return [self._row_to_engagement(r) for r in rows]
        finally:
            conn.close()

    def update_status(self, engagement_id: int, new_status: EngagementStatus, changed_by: int, reason: str = "") -> None:
        conn = get_db_connection(self.db_path)
        now = datetime.now(timezone.utc).isoformat()
        try:
            with conn:
                old = conn.execute("SELECT status FROM engagements WHERE engagement_id = ?;", (engagement_id,)).fetchone()
                old_status = old["status"] if old else "UNKNOWN"
                conn.execute(
                    "UPDATE engagements SET status = ?, updated_at = ? WHERE engagement_id = ?;",
                    (new_status.value, now, engagement_id)
                )
                conn.execute(
                    "INSERT INTO engagement_status_history (engagement_id, old_status, new_status, changed_by, reason, changed_at) VALUES (?, ?, ?, ?, ?, ?);",
                    (engagement_id, old_status, new_status.value, changed_by, reason, now)
                )
        finally:
            conn.close()

    def reassign_operator(self, engagement_id: int, new_operator_id: int) -> bool:
        """Reassign engagement operator to resolve 4-Eyes Principle / SoD conflicts."""
        conn = get_db_connection(self.db_path)
        try:
            with conn:
                conn.execute(
                    "UPDATE engagements SET assigned_to = ? WHERE engagement_id = ?;",
                    (new_operator_id, engagement_id)
                )
                return True
        finally:
            conn.close()

    def get_items(self, engagement_id: int) -> List[EngagementChecklistItem]:
        conn = get_db_connection(self.db_path)
        try:
            rows = conn.execute(
                """
                SELECT * FROM engagement_checklist_items
                WHERE engagement_id = ?
                ORDER BY display_order ASC, engagement_item_id ASC;
                """,
                (engagement_id,)
            ).fetchall()
            return [
                EngagementChecklistItem(
                    engagement_item_id=r["engagement_item_id"],
                    engagement_id=r["engagement_id"],
                    source_item_id=r["source_item_id"],
                    category_name=r["category_name"],
                    document_name_snapshot=r["document_name_snapshot"],
                    requirement_snapshot=RequirementType(r["requirement_snapshot"]),
                    applicability_status=ApplicabilityStatus(r["applicability_status"]),
                    collection_status=DocumentStatus(r["collection_status"]),
                    file_formats=r["file_formats"] if "file_formats" in r.keys() else "PDF, JPG",
                    format_instructions=r["format_instructions"] if "format_instructions" in r.keys() else "",
                    received_date=r["received_date"],
                    verified_by=r["verified_by"],
                    waived_by=r["waived_by"],
                    waiver_reason=r["waiver_reason"] or "",
                    deficiency_reason=r["deficiency_reason"] or "",
                    internal_remarks=r["internal_remarks"] or "",
                    display_order=r["display_order"]
                ) for r in rows
            ]
        finally:
            conn.close()

    def update_item_status(
        self,
        engagement_item_id: int,
        collection_status: DocumentStatus,
        applicability_status: Optional[ApplicabilityStatus] = None,
        verified_by: Optional[int] = None,
        waived_by: Optional[int] = None,
        waiver_reason: str = "",
        deficiency_reason: str = "",
        internal_remarks: str = ""
    ) -> None:
        conn = get_db_connection(self.db_path)
        now = datetime.now(timezone.utc).isoformat()
        try:
            with conn:
                if collection_status == DocumentStatus.NOT_APPLICABLE:
                    applicability_status = ApplicabilityStatus.NOT_APPLICABLE
                elif applicability_status == ApplicabilityStatus.NOT_APPLICABLE:
                    collection_status = DocumentStatus.NOT_APPLICABLE
                elif collection_status in (DocumentStatus.RECEIVED, DocumentStatus.ACCEPTED) and not applicability_status:
                    applicability_status = ApplicabilityStatus.APPLICABLE

                app_part = ""
                params = [collection_status.value]
                if applicability_status:
                    app_part = ", applicability_status = ?"
                    params.append(applicability_status.value)
                if collection_status in (DocumentStatus.RECEIVED, DocumentStatus.ACCEPTED):
                    app_part += ", received_date = ?"
                    params.append(now[:10])
                if verified_by:
                    app_part += ", verified_by = ?"
                    params.append(verified_by)
                if waived_by:
                    app_part += ", waived_by = ?, waiver_reason = ?"
                    params.extend([waived_by, waiver_reason])
                if deficiency_reason:
                    app_part += ", deficiency_reason = ?"
                    params.append(deficiency_reason)
                if internal_remarks:
                    app_part += ", internal_remarks = ?"
                    params.append(internal_remarks)
                params.append(engagement_item_id)

                conn.execute(
                    f"UPDATE engagement_checklist_items SET collection_status = ?{app_part} WHERE engagement_item_id = ?;",
                    tuple(params)
                )
        finally:
            conn.close()

    def add_custom_item(self, engagement_id: int, category_name: str, document_name: str, requirement_type: RequirementType, internal_remarks: str = "") -> int:
        conn = get_db_connection(self.db_path)
        try:
            with conn:
                cur = conn.execute(
                    """
                    INSERT INTO engagement_checklist_items (engagement_id, category_name, document_name_snapshot, requirement_snapshot, applicability_status, collection_status, internal_remarks, display_order)
                    VALUES (?, ?, ?, ?, 'APPLICABLE', 'NOT_REQUESTED', ?, (SELECT COALESCE(MAX(display_order), 0) + 1 FROM engagement_checklist_items WHERE engagement_id = ?));
                    """,
                    (engagement_id, category_name.strip() or "General Documents", document_name.strip(), requirement_type.value, internal_remarks.strip(), engagement_id)
                )
                return cur.lastrowid
        finally:
            conn.close()

    def update_item_remarks(self, engagement_item_id: int, internal_remarks: str, category_name: Optional[str] = None) -> None:
        conn = get_db_connection(self.db_path)
        try:
            with conn:
                if category_name:
                    conn.execute(
                        "UPDATE engagement_checklist_items SET internal_remarks = ?, category_name = ? WHERE engagement_item_id = ?;",
                        (internal_remarks.strip(), category_name.strip(), engagement_item_id)
                    )
                else:
                    conn.execute(
                        "UPDATE engagement_checklist_items SET internal_remarks = ? WHERE engagement_item_id = ?;",
                        (internal_remarks.strip(), engagement_item_id)
                    )
        finally:
            conn.close()

    def toggle_applicability(self, engagement_item_id: int, is_applicable: bool, reason: str = "") -> None:
        conn = get_db_connection(self.db_path)
        try:
            with conn:
                if is_applicable:
                    conn.execute(
                        "UPDATE engagement_checklist_items SET applicability_status = 'APPLICABLE', collection_status = 'NOT_REQUESTED', internal_remarks = ? WHERE engagement_item_id = ?;",
                        (f"Restored to active scope: {reason}".strip(), engagement_item_id)
                    )
                else:
                    conn.execute(
                        "UPDATE engagement_checklist_items SET applicability_status = 'NOT_APPLICABLE', collection_status = 'NOT_APPLICABLE', internal_remarks = ? WHERE engagement_item_id = ?;",
                        (f"Removed from scope / Not Applicable: {reason}".strip(), engagement_item_id)
                    )
        finally:
            conn.close()

    def accept_all_received(self, engagement_id: int, verified_by: int) -> int:
        """Mark all currently received items as verified & accepted in a single batch."""
        conn = get_db_connection(self.db_path)
        now = datetime.now(timezone.utc).isoformat()[:10]
        try:
            with conn:
                cur = conn.execute(
                    """
                    UPDATE engagement_checklist_items
                    SET collection_status = 'ACCEPTED', verified_by = ?, received_date = COALESCE(received_date, ?)
                    WHERE engagement_id = ? AND collection_status = 'RECEIVED' AND applicability_status <> 'NOT_APPLICABLE';
                    """,
                    (verified_by, now, engagement_id)
                )
                return cur.rowcount
        finally:
            conn.close()

    def get_readiness_summary(self, engagement_id: int) -> ReadinessSummary:
        items = self.get_items(engagement_id)
        if not items:
            return ReadinessSummary(is_ready_for_review=False, blocking_reasons=["Checklist is empty."])

        total = len(items)
        mandatory_total = 0
        mandatory_accepted = 0
        conditional_total = 0
        conditional_resolved = 0
        conditional_accepted = 0
        optional_total = 0
        deficient = 0
        blocking_reasons: List[str] = []

        for itm in items:
            req = itm.requirement_snapshot
            status = itm.collection_status
            app = itm.applicability_status

            if status == DocumentStatus.DEFICIENT:
                deficient += 1
                reason_note = itm.deficiency_reason or "Document deficiency reported"
                blocking_reasons.append(f"DEFICIENT: '{itm.document_name_snapshot}' ({reason_note})")

            # Check if item is marked not applicable, waived, or exempt
            is_na = itm.is_exempt

            if req == RequirementType.MANDATORY:
                if is_na:
                    # Formally exempted - does not count towards mandatory total or block readiness
                    pass
                else:
                    mandatory_total += 1
                    if status in (DocumentStatus.ACCEPTED, DocumentStatus.WAIVED_WITH_APPROVAL):
                        mandatory_accepted += 1
                    elif status == DocumentStatus.RECEIVED:
                        blocking_reasons.append(f"PENDING ACCEPTANCE: '{itm.document_name_snapshot}' is Received but not yet Verified & Accepted")
                    else:
                        blocking_reasons.append(f"MISSING: '{itm.document_name_snapshot}' (Status: {status.value})")
            elif req == RequirementType.CONDITIONAL:
                if is_na:
                    # Exempt / waived conditional requirement does not block readiness
                    conditional_resolved += 1
                elif status in (DocumentStatus.ACCEPTED, DocumentStatus.WAIVED_WITH_APPROVAL):
                    conditional_total += 1
                    conditional_resolved += 1
                    conditional_accepted += 1
                elif app == ApplicabilityStatus.APPLICABLE:
                    conditional_total += 1
                    conditional_resolved += 1
                    if status == DocumentStatus.RECEIVED:
                        blocking_reasons.append(f"PENDING ACCEPTANCE: '{itm.document_name_snapshot}' is Received but not yet Verified & Accepted")
                    else:
                        blocking_reasons.append(f"MISSING: '{itm.document_name_snapshot}' (Status: {status.value})")
                else:
                    # Undecided blocks readiness
                    conditional_total += 1
                    blocking_reasons.append(f"UNDECIDED: '{itm.document_name_snapshot}' is Conditional and requires an applicability decision")
            elif req == RequirementType.OPTIONAL:
                optional_total += 1

        applicable_reqs = mandatory_total + conditional_total
        satisfied_reqs = mandatory_accepted + conditional_accepted
        readiness_pct = (satisfied_reqs / applicable_reqs * 100.0) if applicable_reqs > 0 else 100.0

        received_count = sum(
            1 for i in items
            if i.collection_status in (DocumentStatus.RECEIVED, DocumentStatus.UNDER_VERIFICATION, DocumentStatus.ACCEPTED, DocumentStatus.WAIVED_WITH_APPROVAL)
        )
        collection_pct = (received_count / total * 100.0) if total > 0 else 0.0

        # Ready for review requires all applicable mandatory accepted/waived, all conditional resolved & accepted, and zero deficiencies
        is_ready = (
            mandatory_accepted == mandatory_total
            and conditional_accepted == conditional_total
            and deficient == 0
            and len(blocking_reasons) == 0
        )

        return ReadinessSummary(
            total_items=total,
            mandatory_total=mandatory_total,
            mandatory_accepted=mandatory_accepted,
            conditional_total=conditional_total,
            conditional_resolved=conditional_resolved,
            conditional_accepted=conditional_accepted,
            optional_total=optional_total,
            deficient_count=deficient,
            readiness_percentage=round(readiness_pct, 1),
            collection_percentage=round(collection_pct, 1),
            is_ready_for_review=is_ready,
            blocking_reasons=blocking_reasons
        )

    def _row_to_engagement(self, r: sqlite3.Row) -> Engagement:
        return Engagement(
            engagement_id=r["engagement_id"],
            client_id=r["client_id"],
            service_id=r["service_id"],
            variant_id=r["variant_id"],
            financial_year=r["financial_year"] or "2026-2027",
            tax_period=r["tax_period"] or "Annual",
            due_date=r["due_date"] or "",
            priority=Priority(r["priority"]),
            status=EngagementStatus(r["status"]),
            assigned_to=r["assigned_to"] or 0,
            reviewer_id=r["reviewer_id"] or 0,
            notes=r["notes"] or "",
            created_by=r["created_by"] or 1,
            created_at=r["created_at"] or "",
            updated_at=r["updated_at"] or "",
            client_name=r["client_name"] if "client_name" in r.keys() else "",
            service_name=r["service_name"] if "service_name" in r.keys() else "",
            assigned_name=r["assigned_name"] if "assigned_name" in r.keys() else "",
            reviewer_name=r["reviewer_name"] if "reviewer_name" in r.keys() else ""
        )

    def list_pending_follow_ups(self) -> List[dict]:
        """Return active engagements that are overdue for follow-up and still have pending documents.

        An engagement qualifies when:
        - status IN ('NOT_STARTED', 'IN_PROGRESS')
        - The latest follow_up_log.next_follow_up_date <= today  (or no log exists yet)
        - Readiness < 100% (at least one non-exempt item not yet accepted/waived)

        Returns a list of dicts with keys: engagement, pending_count, last_follow_up_date, last_follow_up_user.
        """
        from datetime import date
        today = date.today().isoformat()
        conn = get_db_connection(self.db_path)
        try:
            rows = conn.execute(
                """
                SELECT e.*,
                       c.client_name, s.service_name,
                       u_assigned.full_name as assigned_name,
                       u_reviewer.full_name as reviewer_name,
                       (SELECT f.next_follow_up_date
                        FROM follow_up_logs f
                        WHERE f.engagement_id = e.engagement_id
                        ORDER BY f.created_at DESC LIMIT 1) AS last_next_date,
                       (SELECT f2.communication_mode
                        FROM follow_up_logs f2
                        WHERE f2.engagement_id = e.engagement_id
                        ORDER BY f2.created_at DESC LIMIT 1) AS last_mode
                FROM engagements e
                JOIN clients c ON e.client_id = c.client_id
                JOIN service_templates s ON e.service_id = s.service_id
                LEFT JOIN users u_assigned ON e.assigned_to = u_assigned.user_id
                LEFT JOIN users u_reviewer ON e.reviewer_id = u_reviewer.user_id
                WHERE (e.status = 'IN_PROGRESS' OR (e.status = 'NOT_STARTED' AND datetime(e.created_at) <= datetime('now', '-2 days')))
                  AND (last_next_date IS NULL OR last_next_date <= ?)
                ORDER BY e.due_date ASC;
                """,
                (today,)
            ).fetchall()
        finally:
            conn.close()

        results = []
        for r in rows:
            eng = self._row_to_engagement(r)
            # Count pending (non-exempt, non-accepted, non-waived) items
            items = self.get_items(eng.engagement_id)
            pending = [
                i for i in items
                if not i.is_exempt
                and i.collection_status not in (
                    DocumentStatus.ACCEPTED,
                    DocumentStatus.WAIVED_WITH_APPROVAL,
                    DocumentStatus.NOT_APPLICABLE,
                )
            ]
            if pending:
                results.append({
                    "engagement": eng,
                    "pending_count": len(pending),
                    "last_follow_up_date": r["last_next_date"] or "—",
                    "last_mode": r["last_mode"] or "—",
                })
        return results



class AttachmentRepository:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path

    def add(self, attachment: DocumentAttachment) -> int:
        conn = get_db_connection(self.db_path)
        now = datetime.now(timezone.utc).isoformat()
        try:
            with conn:
                cur = conn.execute(
                    """
                    INSERT INTO document_attachments (
                        engagement_item_id, original_filename, stored_filename, storage_relative_path,
                        file_size_bytes, sha256_hash, uploaded_by, uploaded_at, is_archived
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0);
                    """,
                    (attachment.engagement_item_id, attachment.original_filename, attachment.stored_filename,
                     attachment.storage_relative_path, attachment.file_size_bytes, attachment.sha256_hash,
                     attachment.uploaded_by, now)
                )
                return cur.lastrowid
        finally:
            conn.close()

    def list_by_item(self, engagement_item_id: int) -> List[DocumentAttachment]:
        conn = get_db_connection(self.db_path)
        try:
            rows = conn.execute(
                "SELECT * FROM document_attachments WHERE engagement_item_id = ? AND is_archived = 0;",
                (engagement_item_id,)
            ).fetchall()
            return [
                DocumentAttachment(
                    attachment_id=r["attachment_id"],
                    engagement_item_id=r["engagement_item_id"],
                    original_filename=r["original_filename"],
                    stored_filename=r["stored_filename"],
                    storage_relative_path=r["storage_relative_path"],
                    file_size_bytes=r["file_size_bytes"],
                    sha256_hash=r["sha256_hash"],
                    uploaded_by=r["uploaded_by"],
                    uploaded_at=r["uploaded_at"],
                    is_archived=bool(r["is_archived"])
                ) for r in rows
            ]
        finally:
            conn.close()

    def find_by_hash(self, sha256_hash: str, engagement_item_id: int) -> Optional[DocumentAttachment]:
        """Return an existing attachment if the exact same file content was already uploaded to this checklist item."""
        conn = get_db_connection(self.db_path)
        try:
            r = conn.execute(
                "SELECT * FROM document_attachments WHERE sha256_hash = ? AND engagement_item_id = ? AND is_archived = 0 LIMIT 1;",
                (sha256_hash, engagement_item_id)
            ).fetchone()
            if not r:
                return None
            return DocumentAttachment(
                attachment_id=r["attachment_id"],
                engagement_item_id=r["engagement_item_id"],
                original_filename=r["original_filename"],
                stored_filename=r["stored_filename"],
                storage_relative_path=r["storage_relative_path"],
                file_size_bytes=r["file_size_bytes"],
                sha256_hash=r["sha256_hash"],
                uploaded_by=r["uploaded_by"],
                uploaded_at=r["uploaded_at"]
            )
        finally:
            conn.close()

    def get_attachments_for_engagement(self, engagement_id: int) -> Dict[int, List[DocumentAttachment]]:
        """Return all active attachments grouped by engagement_item_id for an engagement."""
        conn = get_db_connection(self.db_path)
        try:
            rows = conn.execute(
                """
                SELECT a.* FROM document_attachments a
                JOIN engagement_checklist_items i ON a.engagement_item_id = i.engagement_item_id
                WHERE i.engagement_id = ? AND a.is_archived = 0
                ORDER BY a.attachment_id ASC;
                """,
                (engagement_id,)
            ).fetchall()
            res: Dict[int, List[DocumentAttachment]] = {}
            for r in rows:
                iid = r["engagement_item_id"]
                if iid not in res:
                    res[iid] = []
                res[iid].append(
                    DocumentAttachment(
                        attachment_id=r["attachment_id"],
                        engagement_item_id=r["engagement_item_id"],
                        original_filename=r["original_filename"],
                        stored_filename=r["stored_filename"],
                        storage_relative_path=r["storage_relative_path"],
                        file_size_bytes=r["file_size_bytes"],
                        sha256_hash=r["sha256_hash"],
                        uploaded_by=r["uploaded_by"],
                        uploaded_at=r["uploaded_at"]
                    )
                )
            return res
        finally:
            conn.close()


class LogRepository:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path

    def add_audit(self, log: AuditLog) -> None:
        conn = get_db_connection(self.db_path)
        now = datetime.now(timezone.utc).isoformat()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO audit_logs (actor_id, actor_username, event_type, target_entity, target_id, details, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?);
                    """,
                    (log.actor_id, log.actor_username, log.event_type, log.target_entity, log.target_id, log.details, now)
                )
        finally:
            conn.close()

    def add_follow_up(self, follow_up: FollowUpLog) -> int:
        conn = get_db_connection(self.db_path)
        now = datetime.now(timezone.utc).isoformat()
        try:
            with conn:
                cur = conn.execute(
                    """
                    INSERT INTO follow_up_logs (engagement_id, user_id, communication_mode, summary_of_request, client_response, next_follow_up_date, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?);
                    """,
                    (follow_up.engagement_id, follow_up.user_id, follow_up.communication_mode,
                     follow_up.summary_of_request, follow_up.client_response, follow_up.next_follow_up_date, now)
                )
                return cur.lastrowid
        finally:
            conn.close()

    def list_follow_ups(self, engagement_id: int) -> List[FollowUpLog]:
        conn = get_db_connection(self.db_path)
        try:
            rows = conn.execute(
                """
                SELECT f.*, u.full_name as user_name
                FROM follow_up_logs f
                JOIN users u ON f.user_id = u.user_id
                WHERE f.engagement_id = ?
                ORDER BY f.created_at DESC;
                """,
                (engagement_id,)
            ).fetchall()
            return [
                FollowUpLog(
                    log_id=r["log_id"],
                    engagement_id=r["engagement_id"],
                    user_id=r["user_id"],
                    communication_mode=r["communication_mode"],
                    summary_of_request=r["summary_of_request"],
                    client_response=r["client_response"] or "",
                    next_follow_up_date=r["next_follow_up_date"] or "",
                    created_at=r["created_at"],
                    user_name=r["user_name"]
                ) for r in rows
            ]
        finally:
            conn.close()

    def add_review(self, review: ReviewLog) -> int:
        conn = get_db_connection(self.db_path)
        now = datetime.now(timezone.utc).isoformat()
        try:
            with conn:
                cur = conn.execute(
                    """
                    INSERT INTO review_logs (engagement_id, reviewer_id, action, observations, created_at)
                    VALUES (?, ?, ?, ?, ?);
                    """,
                    (review.engagement_id, review.reviewer_id, review.action, review.observations, now)
                )
                return cur.lastrowid
        finally:
            conn.close()

    def list_reviews(self, engagement_id: int) -> List[ReviewLog]:
        conn = get_db_connection(self.db_path)
        try:
            rows = conn.execute(
                """
                SELECT r.*, u.full_name as reviewer_name
                FROM review_logs r
                JOIN users u ON r.reviewer_id = u.user_id
                WHERE r.engagement_id = ?
                ORDER BY r.created_at DESC;
                """,
                (engagement_id,)
            ).fetchall()
            return [
                ReviewLog(
                    review_id=r["review_id"],
                    engagement_id=r["engagement_id"],
                    reviewer_id=r["reviewer_id"],
                    action=r["action"],
                    observations=r["observations"],
                    created_at=r["created_at"],
                    reviewer_name=r["reviewer_name"]
                ) for r in rows
            ]
        finally:
            conn.close()

    # ── Firm Wiki & Knowledge Management ─────────────────────────────────────
    def add_knowledge(self, title: str, service_group: str, content: str, category: str = "SOP") -> int:
        return KnowledgeRepository(self.db_path).add_knowledge(title, service_group, content, category)

    def update_knowledge(self, doc_id: int, title: str, content: str, service_group: Optional[str] = None) -> bool:
        return KnowledgeRepository(self.db_path).update_knowledge(doc_id, title, content, service_group)

    def delete_knowledge(self, doc_id: int) -> bool:
        return KnowledgeRepository(self.db_path).delete_knowledge(doc_id)


class KnowledgeRepository:
    """Repository for firm-wide knowledge documents, procedural SOPs, and FTS5 indexing."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path

    def add_knowledge(self, title: str, service_group: str, content: str, category: str = "SOP") -> int:
        conn = get_db_connection(self.db_path)
        now = datetime.now(timezone.utc).isoformat()
        try:
            with conn:
                cur = conn.execute(
                    """
                    INSERT INTO knowledge_documents (title, service_group, category, content, created_at)
                    VALUES (?, ?, ?, ?, ?);
                    """,
                    (title.strip(), service_group.strip(), category.strip(), content.strip(), now)
                )
                doc_id = cur.lastrowid
                try:
                    conn.execute("INSERT INTO knowledge_fts(knowledge_fts) VALUES('rebuild');")
                except Exception:
                    pass
                return doc_id
        finally:
            conn.close()

    def update_knowledge(self, doc_id: int, title: str, content: str, service_group: Optional[str] = None) -> bool:
        conn = get_db_connection(self.db_path)
        try:
            with conn:
                if service_group:
                    cur = conn.execute(
                        """
                        UPDATE knowledge_documents
                        SET title = ?, service_group = ?, content = ?
                        WHERE doc_id = ?;
                        """,
                        (title.strip(), service_group.strip(), content.strip(), doc_id)
                    )
                else:
                    cur = conn.execute(
                        """
                        UPDATE knowledge_documents
                        SET title = ?, content = ?
                        WHERE doc_id = ?;
                        """,
                        (title.strip(), content.strip(), doc_id)
                    )
                try:
                    conn.execute("INSERT INTO knowledge_fts(knowledge_fts) VALUES('rebuild');")
                except Exception:
                    pass
                return cur.rowcount > 0
        finally:
            conn.close()

    def delete_knowledge(self, doc_id: int) -> bool:
        conn = get_db_connection(self.db_path)
        try:
            with conn:
                cur = conn.execute("DELETE FROM knowledge_documents WHERE doc_id = ?;", (doc_id,))
                try:
                    conn.execute("INSERT INTO knowledge_fts(knowledge_fts) VALUES('rebuild');")
                except Exception:
                    pass
                return cur.rowcount > 0
        finally:
            conn.close()

    def get_knowledge(self, doc_id: int) -> Optional[Dict[str, Any]]:
        conn = get_db_connection(self.db_path)
        try:
            row = conn.execute("SELECT * FROM knowledge_documents WHERE doc_id = ?;", (doc_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_all(self) -> List[Dict[str, Any]]:
        conn = get_db_connection(self.db_path)
        try:
            rows = conn.execute(
                "SELECT * FROM knowledge_documents ORDER BY doc_id DESC;"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def list_groups(self) -> List[str]:
        conn = get_db_connection(self.db_path)
        try:
            rows = conn.execute(
                "SELECT DISTINCT service_group FROM knowledge_documents WHERE service_group != '' ORDER BY service_group;"
            ).fetchall()
            return [r[0] for r in rows if r[0]]
        finally:
            conn.close()

    def count_articles(self) -> int:
        conn = get_db_connection(self.db_path)
        try:
            row = conn.execute("SELECT COUNT(*) FROM knowledge_documents;").fetchone()
            return row[0] if row else 0
        finally:
            conn.close()

    def find_guidance(self, search_term: str) -> Optional[Dict[str, Any]]:
        """Contextually retrieve SOP guidance for a given document snapshot name."""
        clean = search_term.strip()
        if not clean:
            return None
        conn = get_db_connection(self.db_path)
        try:
            # 1. Exact or close substring match in title or content
            row = conn.execute(
                """
                SELECT doc_id, title, service_group, content
                FROM knowledge_documents
                WHERE title LIKE ? OR content LIKE ?
                ORDER BY CASE WHEN title LIKE ? THEN 1 ELSE 2 END, doc_id ASC
                LIMIT 1;
                """,
                (f"%{clean}%", f"%{clean}%", f"%{clean}%")
            ).fetchone()
            if row:
                return dict(row)

            # 2. Extract compound key terms first (e.g. "Form 16", "26AS", "PAN", "Aadhaar", "Rent Agreement", "NOC", "SPICe+")
            import re
            compound = re.findall(r'(?:Form\s+\d+\w*|\b\d{2}[A-Z]{2}\b|[A-Z]{2,4}-\d+[A-Z]*|SPICe\+?)', clean, re.IGNORECASE)
            for cp in compound:
                row = conn.execute(
                    """
                    SELECT doc_id, title, service_group, content
                    FROM knowledge_documents
                    WHERE title LIKE ? OR content LIKE ?
                    LIMIT 1;
                    """,
                    (f"%{cp}%", f"%{cp}%")
                ).fetchone()
                if row:
                    return dict(row)

            # 3. Extract individual key terms
            tokens = [t for t in re.split(r'[\s\(\)/,\-\.]+', clean) if len(t) >= 3 and t.lower() not in (
                'from', 'and', 'for', 'the', 'with', 'all', 'part', 'active', 'accounts', 'statement', 'statements'
            )]
            for token in tokens:
                row = conn.execute(
                    """
                    SELECT doc_id, title, service_group, content
                    FROM knowledge_documents
                    WHERE title LIKE ? OR content LIKE ?
                    LIMIT 1;
                    """,
                    (f"%{token}%", f"%{token}%")
                ).fetchone()
                if row:
                    return dict(row)

            # 4. FTS match fallback
            try:
                fts_query = tokens[0] if tokens else clean
                fts_row = conn.execute(
                    """
                    SELECT rowid as doc_id, title, service_group, content
                    FROM knowledge_fts
                    WHERE knowledge_fts MATCH ?
                    ORDER BY rank
                    LIMIT 1;
                    """,
                    (f'"{fts_query}"' if " " in fts_query else f"{fts_query}*",)
                ).fetchone()
                if fts_row:
                    return dict(fts_row)
            except Exception:
                pass

            return None
        finally:
            conn.close()
