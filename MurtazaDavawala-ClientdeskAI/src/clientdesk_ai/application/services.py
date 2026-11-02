"""Application service orchestrating authentication, clients, engagements, checklists, files, and review."""

import re
import shutil
import sqlite3
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
import keyring

from src.clientdesk_ai.config.settings import CONFIG
from src.clientdesk_ai.domain.models import (
    User, UserRole, Client, Engagement, EngagementChecklistItem, DocumentAttachment,
    FollowUpLog, ReviewLog, AuditLog, ReadinessSummary, RequirementType, DocumentStatus,
    ApplicabilityStatus, Priority, EngagementStatus
)
from src.clientdesk_ai.persistence.repositories import (
    UserRepository, ClientRepository, TemplateRepository, EngagementRepository,
    AttachmentRepository, LogRepository
)
from src.clientdesk_ai.security.crypto import (
    verify_password, hash_password, generate_session_token, compute_file_sha256,
    mask_pan, mask_gstin
)


class AuthService:
    def __init__(self, user_repo: Optional[UserRepository] = None, log_repo: Optional[LogRepository] = None):
        self.user_repo = user_repo or UserRepository()
        self.log_repo = log_repo or LogRepository()

    def authenticate(self, username: str, password: str) -> Tuple[bool, Optional[User], str]:
        """Authenticate user with rate-limiting lock check and constant-time password verification."""
        clean_user = username.strip()
        if not clean_user:
            return False, None, "Username cannot be empty."

        failed_count = self.user_repo.count_recent_failed_attempts(clean_user)
        if failed_count >= CONFIG.max_login_attempts:
            return False, None, f"Account temporarily locked due to {failed_count} failed attempts. Please wait 15 minutes."

        user = self.user_repo.get_by_username(clean_user)
        if not user or not user.is_active:
            self.user_repo.record_login_attempt(clean_user, False)
            return False, None, "Invalid username or password."

        if not verify_password(password, user.password_hash):
            self.user_repo.record_login_attempt(clean_user, False)
            return False, None, "Invalid username or password."

        self.user_repo.record_login_attempt(clean_user, True)
        self.log_repo.add_audit(
            AuditLog(actor_id=user.user_id, actor_username=user.username, event_type="LOGIN", target_entity="USER", target_id=str(user.user_id), details="User logged in successfully")
        )
        return True, user, "Login successful."


class ClientService:
    def __init__(self, client_repo: Optional[ClientRepository] = None, log_repo: Optional[LogRepository] = None):
        self.client_repo = client_repo or ClientRepository()
        self.log_repo = log_repo or LogRepository()

    def _validate_identifiers(self, client: Client) -> Tuple[bool, str]:
        """Validate optional tax and identity numbers: PAN, Aadhaar, and GSTIN."""
        # 1. PAN validation (optional, but if provided must follow statutory format: 5 letters + 4 digits + 1 letter)
        clean_pan = client.pan.strip().upper() if client.pan else ""
        if clean_pan:
            if not re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]$', clean_pan):
                return False, f"Invalid PAN format '{clean_pan}'. PAN must be 10 characters: 5 uppercase letters, 4 digits, and 1 letter (e.g. ABCDE1234F)."
            client.pan = clean_pan

        # 2. Aadhaar validation (optional, but if provided must be exactly 12 numerical digits)
        raw_aadhaar = getattr(client, "aadhaar", "") or ""
        clean_aadhaar = re.sub(r'[\s\-]', '', raw_aadhaar.strip())
        if clean_aadhaar:
            if not re.match(r'^[0-9]{12}$', clean_aadhaar):
                return False, f"Invalid Aadhaar format. Aadhaar must be exactly 12 numerical digits (e.g. 1234 5678 9012)."
            client.aadhaar = clean_aadhaar

        # 3. GSTIN validation (optional, but if provided must follow statutory 15-char alphanumeric format)
        clean_gstin = client.gstin.strip().upper() if client.gstin else ""
        if clean_gstin:
            if not re.match(r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$', clean_gstin):
                return False, f"Invalid GSTIN format '{clean_gstin}'. GSTIN must be 15 alphanumeric characters (e.g. 27ABCDE1234F1Z5)."
            if clean_pan and clean_gstin[2:12] != clean_pan:
                return False, f"GSTIN does not match PAN. Characters 3-12 of GSTIN ('{clean_gstin[2:12]}') must match PAN ('{clean_pan}')."
            client.gstin = clean_gstin

        return True, ""

    def register_client(self, client: Client, actor: Optional[User] = None) -> Tuple[bool, Optional[Client], str]:
        """Register a new client with duplicate code and identifier verification."""
        if not client.client_code.strip():
            return False, None, "Client Code is required."
        if not client.client_name.strip():
            return False, None, "Client Name is required."

        existing = self.client_repo.get_by_code(client.client_code)
        if existing:
            return False, None, f"Client code '{client.client_code}' already exists. Please choose a unique code."

        ok_id, err_id = self._validate_identifiers(client)
        if not ok_id:
            return False, None, err_id

        actor_id = actor.user_id if actor else (client.created_by or 1)
        actor_name = actor.username if actor else "system"
        client.created_by = actor_id

        client_id = self.client_repo.create(client)
        client.client_id = client_id

        self.log_repo.add_audit(
            AuditLog(
                actor_id=actor_id,
                actor_username=actor_name,
                event_type="CREATE_CLIENT",
                target_entity="CLIENT",
                target_id=str(client_id),
                details=f"Registered client {client.client_name} ({client.client_code})"
            )
        )
        return True, client, "Client registered successfully."

    def update_client(self, client: Client, actor: Optional[User] = None) -> Tuple[bool, str]:
        """Update existing client record with identifier validation and audit logging."""
        if not client.client_name.strip():
            return False, "Client Name is required."

        ok_id, err_id = self._validate_identifiers(client)
        if not ok_id:
            return False, err_id

        self.client_repo.update(client)

        actor_id = actor.user_id if actor else (client.created_by or 1)
        actor_name = actor.username if actor else "system"
        self.log_repo.add_audit(
            AuditLog(
                actor_id=actor_id,
                actor_username=actor_name,
                event_type="UPDATE_CLIENT",
                target_entity="CLIENT",
                target_id=str(client.client_id),
                details=f"Updated client master record for {client.client_name} ({client.client_code})"
            )
        )
        return True, f"Client record for '{client.client_name}' was updated successfully."

    def search_clients(self, query: str = "") -> List[Client]:
        return self.client_repo.search(query)


class EngagementService:
    def __init__(
        self,
        engagement_repo: Optional[EngagementRepository] = None,
        template_repo: Optional[TemplateRepository] = None,
        log_repo: Optional[LogRepository] = None
    ):
        self.engagement_repo = engagement_repo or EngagementRepository()
        self.template_repo = template_repo or TemplateRepository()
        self.log_repo = log_repo or LogRepository()

    def create_engagement(self, engagement: Engagement, actor: User) -> Tuple[bool, Optional[int], str]:
        """Create new engagement, applying immutable checklist item snapshot from approved service template."""
        if engagement.client_id <= 0:
            return False, None, "Valid client selection is required."
        if engagement.service_id <= 0:
            return False, None, "Valid service template selection is required."
        if not engagement.due_date:
            return False, None, "Due date is required."

        engagement.created_by = actor.user_id
        engagement.status = EngagementStatus.NOT_STARTED

        engagement_id = self.engagement_repo.create(engagement)

        self.log_repo.add_audit(
            AuditLog(
                actor_id=actor.user_id, actor_username=actor.username, event_type="CREATE_ENGAGEMENT",
                target_entity="ENGAGEMENT", target_id=str(engagement_id),
                details=f"Created engagement for client_id {engagement.client_id}, service_id {engagement.service_id}"
            )
        )
        return True, engagement_id, "Engagement created and checklist snapshotted successfully."

    def list_engagements(self, client_id: Optional[int] = None, assigned_to: Optional[int] = None, status: Optional[str] = None) -> List[Engagement]:
        return self.engagement_repo.list_all(client_id=client_id, assigned_to=assigned_to, status=status)

    def get_readiness(self, engagement_id: int) -> ReadinessSummary:
        return self.engagement_repo.get_readiness_summary(engagement_id)

    def submit_for_review(self, engagement_id: int, actor: User) -> Tuple[bool, str]:
        """Submit engagement to senior review queue after checking mandatory readiness."""
        summary = self.get_readiness(engagement_id)
        if not summary.is_ready_for_review:
            reasons = ("\n• " + "\n• ".join(summary.blocking_reasons)) if summary.blocking_reasons else ""
            return False, (
                f"Cannot submit for review: {summary.mandatory_total - summary.mandatory_accepted} mandatory items remaining, "
                f"or deficiencies unresolved.{reasons}"
            )

        self.engagement_repo.update_status(
            engagement_id, EngagementStatus.SUBMITTED_FOR_REVIEW, actor.user_id, "Submitted by staff for senior review"
        )
        self.log_repo.add_audit(
            AuditLog(
                actor_id=actor.user_id, actor_username=actor.username, event_type="SUBMIT_FOR_REVIEW",
                target_entity="ENGAGEMENT", target_id=str(engagement_id), details="Engagement submitted for senior review"
            )
        )
        return True, "Engagement submitted for senior review successfully."

    def perform_review(self, engagement_id: int, reviewer: User, is_approved: bool, observations: str) -> Tuple[bool, str]:
        """Perform senior review: staff cannot review/approve their own engagement."""
        eng = self.engagement_repo.get_by_id(engagement_id)
        if not eng:
            return False, "Engagement not found."

        # Segregation of duties: the assigned operator cannot review their own engagement, regardless of role
        if eng.assigned_to == reviewer.user_id:
            return False, "Segregation of Duties Violation: You cannot review or approve an engagement assigned to yourself."

        action = "APPROVED" if is_approved else "RETURNED_FOR_CORRECTION"
        new_status = EngagementStatus.APPROVED if is_approved else EngagementStatus.RETURNED_FOR_CORRECTION

        self.log_repo.add_review(
            ReviewLog(engagement_id=engagement_id, reviewer_id=reviewer.user_id, action=action, observations=observations)
        )
        self.engagement_repo.update_status(engagement_id, new_status, reviewer.user_id, observations)

        self.log_repo.add_audit(
            AuditLog(
                actor_id=reviewer.user_id, actor_username=reviewer.username, event_type=f"REVIEW_{action}",
                target_entity="ENGAGEMENT", target_id=str(engagement_id), details=f"Review decision: {action}. Remarks: {observations}"
            )
        )
        return True, f"Review completed with status: {action}."


class ChecklistService:
    def __init__(self, engagement_repo: Optional[EngagementRepository] = None, log_repo: Optional[LogRepository] = None):
        self.engagement_repo = engagement_repo or EngagementRepository()
        self.log_repo = log_repo or LogRepository()

    def update_item_status(
        self,
        item_id: int,
        status: DocumentStatus,
        actor: User,
        applicability: Optional[ApplicabilityStatus] = None,
        waiver_reason: str = "",
        deficiency_reason: str = "",
        remarks: str = ""
    ) -> Tuple[bool, str]:
        """Update checklist item collection/verification status with waiver and deficiency validation."""
        # Waiver requires authorized role and recorded reason
        waived_by = None
        if status == DocumentStatus.WAIVED_WITH_APPROVAL:
            if actor.role not in (UserRole.ADMIN, UserRole.PARTNER, UserRole.SENIOR):
                return False, "Only Administrators, Partners, or Seniors can waive a document requirement."
            if not waiver_reason.strip():
                return False, "A documented justification reason is mandatory to waive a document requirement."
            waived_by = actor.user_id

        verified_by = actor.user_id if status == DocumentStatus.ACCEPTED else None

        self.engagement_repo.update_item_status(
            engagement_item_id=item_id,
            collection_status=status,
            applicability_status=applicability,
            verified_by=verified_by,
            waived_by=waived_by,
            waiver_reason=waiver_reason,
            deficiency_reason=deficiency_reason,
            internal_remarks=remarks
        )

        self.log_repo.add_audit(
            AuditLog(
                actor_id=actor.user_id, actor_username=actor.username, event_type="UPDATE_DOCUMENT_STATUS",
                target_entity="CHECKLIST_ITEM", target_id=str(item_id),
                details=f"Status set to {status.value}. Reason: {waiver_reason or deficiency_reason}"
            )
        )
        return True, f"Document status updated to {status.value}."


class AttachmentService:
    def __init__(
        self,
        attachment_repo: Optional[AttachmentRepository] = None,
        log_repo: Optional[LogRepository] = None,
        storage_root: Optional[Path] = None
    ):
        self.attachment_repo = attachment_repo or AttachmentRepository()
        self.log_repo = log_repo or LogRepository()
        self.storage_root = storage_root or CONFIG.filestore_path

    def attach_file(self, source_path: Path, engagement_item_id: int, actor: User) -> Tuple[bool, Optional[DocumentAttachment], str]:
        """Safely copy file into managed storage folder with SHA-256 duplicate warning and path containment."""
        if not source_path.exists() or not source_path.is_file():
            return False, None, "Source file does not exist."

        ext = source_path.suffix.lower()
        if ext not in CONFIG.allowed_file_types:
            return False, None, f"File type '{ext}' is not permitted. Allowed: {', '.join(CONFIG.allowed_file_types)}"

        file_size = source_path.stat().st_size
        if file_size > CONFIG.max_upload_size_mb * 1024 * 1024:
            return False, None, f"File exceeds maximum size limit of {CONFIG.max_upload_size_mb} MB."

        sha256 = compute_file_sha256(source_path)

        # Block exact duplicate: same file content already attached to this specific checklist item
        duplicate = self.attachment_repo.find_by_hash(sha256, engagement_item_id)
        if duplicate:
            return False, None, "This exact file has already been uploaded for this checklist item."

        # Construct safe storage path
        item_folder = self.storage_root / f"item_{engagement_item_id}"
        item_folder.mkdir(parents=True, exist_ok=True)

        now_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        safe_filename = f"doc_{now_str}_{sha256[:8]}{ext}"
        destination = item_folder / safe_filename

        shutil.copy2(source_path, destination)

        rel_path = str(destination.relative_to(self.storage_root))
        attachment = DocumentAttachment(
            engagement_item_id=engagement_item_id,
            original_filename=source_path.name,
            stored_filename=safe_filename,
            storage_relative_path=rel_path,
            file_size_bytes=file_size,
            sha256_hash=sha256,
            uploaded_by=actor.user_id
        )

        try:
            att_id = self.attachment_repo.add(attachment)
        except sqlite3.IntegrityError:
            # UNIQUE(engagement_item_id, sha256_hash) constraint — exact duplicate at DB level
            return False, None, "This exact file has already been uploaded for this checklist item."

        attachment.attachment_id = att_id

        self.log_repo.add_audit(
            AuditLog(
                actor_id=actor.user_id, actor_username=actor.username, event_type="UPLOAD_ATTACHMENT",
                target_entity="DOCUMENT_ATTACHMENT", target_id=str(att_id),
                details=f"Attached '{source_path.name}' ({file_size} bytes, SHA256: {sha256[:12]}...)"
            )
        )
        return True, attachment, "File attached successfully."

    def get_attachments_for_engagement(self, engagement_id: int) -> Dict[int, List[DocumentAttachment]]:
        """Return all active attachments for an engagement grouped by item id."""
        return self.attachment_repo.get_attachments_for_engagement(engagement_id)

    def get_attachment_file_path(self, attachment: DocumentAttachment) -> Path:
        """Resolve absolute on-disk path for an attachment."""
        return self.storage_root / attachment.storage_relative_path

    def list_by_item(self, item_id: int) -> List[DocumentAttachment]:
        """Return all active attachments for a specific checklist item."""
        return self.attachment_repo.list_by_item(item_id)


_FTS_TOKEN = re.compile(r"[0-9A-Za-z\u0900-\u097F]+")


class KnowledgeSearchService:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path

    def search(self, query_text: str, service_group: Optional[str] = None) -> List[Dict[str, Any]]:
        """Search local SOP knowledge articles using robust SQLite FTS5 with BM25 ranking and LIKE fallback."""
        clean = (query_text or "").strip()
        tokens = _FTS_TOKEN.findall(clean)[:12]
        from src.clientdesk_ai.persistence.database import get_db_connection
        conn = get_db_connection(self.db_path)
        try:
            # 1. Empty or wildcard search -> return all articles (optionally filtered by service_group)
            if not tokens or clean in ("", "*"):
                sql = "SELECT doc_id, title, service_group, category, content as snippet, content FROM knowledge_documents WHERE 1=1"
                params: List[Any] = []
                if service_group and service_group not in ("All Service Groups", "All", ""):
                    sql += " AND service_group = ?"
                    params.append(service_group)
                sql += " ORDER BY doc_id DESC LIMIT 100;"
                rows = conn.execute(sql, params).fetchall()
                return [dict(r) for r in rows]

            # 2. Build sanitized FTS5 prefix match: e.g. "turnover"* "threshold"*
            fts_q = " ".join(f'"{t}"*' for t in tokens)
            sql = (
                "SELECT a.doc_id, a.title, a.service_group, a.category, "
                "snippet(knowledge_fts, 2, '<b>', '</b>', '...', 20) as snippet, a.content "
                "FROM knowledge_fts k "
                "JOIN knowledge_documents a ON a.doc_id = k.rowid "
                "WHERE knowledge_fts MATCH ?"
            )
            params = [fts_q]
            if service_group and service_group not in ("All Service Groups", "All", ""):
                sql += " AND a.service_group = ?"
                params.append(service_group)
            sql += " ORDER BY bm25(knowledge_fts, 5.0, 2.0, 1.0) LIMIT 50;"

            rows = []
            try:
                rows = conn.execute(sql, params).fetchall()
            except Exception:
                rows = []

            # 3. Try OR-based FTS5 prefix match if strict AND returned no rows
            if not rows and len(tokens) > 1:
                fts_or = " OR ".join(f'"{t}"*' for t in tokens)
                sql_or = (
                    "SELECT a.doc_id, a.title, a.service_group, a.category, "
                    "snippet(knowledge_fts, 2, '<b>', '</b>', '...', 20) as snippet, a.content "
                    "FROM knowledge_fts k "
                    "JOIN knowledge_documents a ON a.doc_id = k.rowid "
                    "WHERE knowledge_fts MATCH ?"
                )
                p_or = [fts_or]
                if service_group and service_group not in ("All Service Groups", "All", ""):
                    sql_or += " AND a.service_group = ?"
                    p_or.append(service_group)
                sql_or += " ORDER BY bm25(knowledge_fts, 5.0, 2.0, 1.0) LIMIT 50;"
                try:
                    rows = conn.execute(sql_or, p_or).fetchall()
                except Exception:
                    rows = []

            # If FTS match found rows, return them
            if rows:
                return [dict(r) for r in rows]

            # 4. Fallback: Flexible LIKE across title, content, service_group, and category
            sql_fallback = (
                "SELECT doc_id, title, service_group, category, content as snippet, content "
                "FROM knowledge_documents WHERE ("
            )
            conds = []
            l_params: List[Any] = []
            for t in tokens:
                conds.append("(title LIKE ? OR content LIKE ? OR service_group LIKE ? OR category LIKE ?)")
                l_params.extend([f"%{t}%", f"%{t}%", f"%{t}%", f"%{t}%"])
            sql_fallback += " OR ".join(conds) + ")"
            if service_group and service_group not in ("All Service Groups", "All", ""):
                sql_fallback += " AND service_group = ?"
                l_params.append(service_group)
            sql_fallback += " ORDER BY CASE WHEN title LIKE ? THEN 1 WHEN content LIKE ? THEN 2 ELSE 3 END, doc_id DESC LIMIT 50;"
            l_params.append(f"%{clean}%")
            l_params.append(f"%{clean}%")

            rows = conn.execute(sql_fallback, l_params).fetchall()
            if rows:
                return [dict(r) for r in rows]

            # 5. If group filter yielded 0 results, retry globally across all service groups
            if service_group and service_group not in ("All Service Groups", "All", ""):
                return self.search(query_text, service_group=None)

            return []
        except Exception:
            return []
        finally:
            conn.close()

    def rebuild_index(self) -> None:
        """Explicitly synchronize/rebuild SQLite FTS5 full-text index."""
        from src.clientdesk_ai.persistence.database import get_db_connection
        conn = get_db_connection(self.db_path)
        try:
            with conn:
                conn.execute("INSERT INTO knowledge_fts(knowledge_fts) VALUES('rebuild');")
        except Exception:
            pass
        finally:
            conn.close()


class EmailService:
    """Outbound SMTP email dispatch service with secure OS credential storage via keyring."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or CONFIG.db_path

    def get_smtp_config(self) -> Dict[str, Any]:
        """Fetch SMTP configuration settings from app_settings and keyring."""
        from src.clientdesk_ai.persistence.database import get_db_connection
        conn = get_db_connection(self.db_path)
        settings = {
            "smtp_host": "smtp.gmail.com",
            "smtp_port": "587",
            "smtp_user": "",
            "smtp_use_tls": "1",
        }
        try:
            rows = conn.execute(
                "SELECT setting_key, setting_value FROM app_settings WHERE setting_key LIKE 'smtp_%';"
            ).fetchall()
            for r in rows:
                settings[r["setting_key"]] = r["setting_value"]
        finally:
            conn.close()

        has_password = False
        try:
            pw = keyring.get_password("clientdesk", "smtp_pass")
            has_password = bool(pw)
        except Exception:
            has_password = False

        return {
            "smtp_host": settings.get("smtp_host", "smtp.gmail.com"),
            "smtp_port": int(settings.get("smtp_port", 587)),
            "smtp_user": settings.get("smtp_user", ""),
            "smtp_use_tls": settings.get("smtp_use_tls", "1") == "1",
            "has_password": has_password,
        }

    def save_smtp_config(
        self, host: str, port: int, user: str, use_tls: bool = True, password: Optional[str] = None
    ) -> Tuple[bool, str]:
        """Save SMTP host, port, user, TLS setting to SQLite, and password to OS keyring."""
        from src.clientdesk_ai.persistence.database import get_db_connection
        conn = get_db_connection(self.db_path)
        now = datetime.now(timezone.utc).isoformat()
        try:
            with conn:
                entries = [
                    ("smtp_host", host.strip()),
                    ("smtp_port", str(port)),
                    ("smtp_user", user.strip()),
                    ("smtp_use_tls", "1" if use_tls else "0"),
                ]
                for k, v in entries:
                    conn.execute(
                        """
                        INSERT INTO app_settings (setting_key, setting_value, updated_at)
                        VALUES (?, ?, ?)
                        ON CONFLICT(setting_key) DO UPDATE SET
                            setting_value = excluded.setting_value,
                            updated_at = excluded.updated_at;
                        """,
                        (k, v, now)
                    )
        except Exception as e:
            return False, f"Failed to save settings: {e}"
        finally:
            conn.close()

        if password is not None and password != "":
            try:
                keyring.set_password("clientdesk", "smtp_pass", password)
            except Exception as e:
                return False, f"Failed to save password securely in keyring: {e}"

        return True, "Email settings saved successfully."

    def send_checklist_email(
        self, to_email: str, subject: str, body_text: str, pdf_path: Optional[str] = None
    ) -> Tuple[bool, str]:
        """Send checklist email with optional PDF attachment via configured SMTP server."""
        cfg = self.get_smtp_config()
        host = cfg.get("smtp_host")
        port = cfg.get("smtp_port", 587)
        user = cfg.get("smtp_user")
        use_tls = cfg.get("smtp_use_tls", True)

        if not host or not user:
            return False, "SMTP Host or Sender Email is not configured. Please complete SMTP configuration in Settings."

        if not to_email or "@" not in to_email:
            return False, f"Invalid recipient email address: '{to_email}'"

        try:
            password = keyring.get_password("clientdesk", "smtp_pass")
        except Exception as e:
            return False, f"Could not retrieve SMTP password from secure storage: {e}"

        if not password:
            return False, "SMTP App Password is not set. Please set the password in Settings."

        # Construct MIME Message
        message = MIMEMultipart()
        message["Subject"] = subject
        message["From"] = user
        message["To"] = to_email

        # Attach text/plain or HTML
        if "<html" in body_text.lower() or "</div>" in body_text.lower() or "<br" in body_text.lower():
            message.attach(MIMEText(body_text, "html", "utf-8"))
        else:
            message.attach(MIMEText(body_text, "plain", "utf-8"))

        # Attach PDF if exists
        if pdf_path:
            p = Path(pdf_path)
            if p.exists() and p.is_file():
                try:
                    with open(p, "rb") as f:
                        pdf_data = f.read()
                    part = MIMEApplication(pdf_data, _subtype="pdf")
                    part.add_header("Content-Disposition", "attachment", filename=p.name)
                    message.attach(part)
                except Exception as e:
                    return False, f"Failed to read and attach PDF file: {e}"

        # Connect and send
        try:
            if port == 465:
                # SSL
                with smtplib.SMTP_SSL(host, port, timeout=20) as server:
                    server.login(user, password)
                    server.send_message(message)
            else:
                # STARTTLS or plain
                with smtplib.SMTP(host, port, timeout=20) as server:
                    server.ehlo()
                    if use_tls:
                        server.starttls()
                        server.ehlo()
                    server.login(user, password)
                    server.send_message(message)
            return True, "Email sent successfully."
        except smtplib.SMTPAuthenticationError as exc:
            err_msg = exc.smtp_error.decode(errors="replace") if isinstance(exc.smtp_error, bytes) else str(exc)
            return False, f"SMTP Authentication Error (Check email and app password): {err_msg}"
        except (smtplib.SMTPConnectError, ConnectionError, TimeoutError, OSError) as exc:
            return False, f"SMTP Connection Error (Could not connect to {host}:{port}): {exc}"
        except Exception as exc:
            return False, f"Failed to send email: {exc}"

