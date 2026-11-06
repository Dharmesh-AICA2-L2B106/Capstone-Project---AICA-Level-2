"""Domain entities, value objects, and status enumeration rules."""

from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
from typing import Optional, List, Dict, Any


class UserRole(str, Enum):
    ADMIN = "ADMIN"
    PARTNER = "PARTNER"
    SENIOR = "SENIOR"
    STAFF = "STAFF"
    READ_ONLY = "READ_ONLY"


class RequirementType(str, Enum):
    MANDATORY = "MANDATORY"
    CONDITIONAL = "CONDITIONAL"
    OPTIONAL = "OPTIONAL"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class EngagementStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    SUBMITTED_FOR_REVIEW = "SUBMITTED_FOR_REVIEW"
    UNDER_REVIEW = "UNDER_REVIEW"
    RETURNED_FOR_CORRECTION = "RETURNED_FOR_CORRECTION"
    APPROVED = "APPROVED"
    COMPLETED = "COMPLETED"
    ON_HOLD = "ON_HOLD"
    CANCELLED = "CANCELLED"
    REOPENED = "REOPENED"


class DocumentStatus(str, Enum):
    NOT_REQUESTED = "NOT_REQUESTED"
    REQUESTED = "REQUESTED"
    RECEIVED = "RECEIVED"
    UNDER_VERIFICATION = "UNDER_VERIFICATION"
    ACCEPTED = "ACCEPTED"
    DEFICIENT = "DEFICIENT"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    WAIVED_WITH_APPROVAL = "WAIVED_WITH_APPROVAL"


class ApplicabilityStatus(str, Enum):
    UNDECIDED = "UNDECIDED"
    APPLICABLE = "APPLICABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class Priority(str, Enum):
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    URGENT = "URGENT"


@dataclass
class User:
    user_id: int = 0
    username: str = ""
    full_name: str = ""
    email: str = ""
    password_hash: str = ""
    role: UserRole = UserRole.STAFF
    is_active: bool = True
    created_at: str = ""
    last_login: Optional[str] = None


@dataclass
class Client:
    client_id: int = 0
    client_code: str = ""
    client_name: str = ""
    trade_name: str = ""
    entity_type: str = "Sole Proprietorship"
    pan: str = ""
    aadhaar: str = ""
    gstin: str = ""
    email: str = ""
    phone: str = ""
    address: str = ""
    status: str = "ACTIVE"
    created_by: int = 0
    created_at: str = ""
    updated_at: str = ""


@dataclass
class ServiceTemplate:
    service_id: int = 0
    service_code: str = ""
    service_name: str = ""
    service_group: str = ""
    description: str = ""
    is_active: bool = True
    created_at: str = ""


@dataclass
class TemplateVariant:
    variant_id: int = 0
    service_id: int = 0
    variant_code: str = ""
    variant_name: str = ""
    description: str = ""
    is_active: bool = True


@dataclass
class ChecklistItem:
    item_id: int = 0
    service_id: int = 0
    variant_id: Optional[int] = None
    category_name: str = "General Documents"
    document_name: str = ""
    requirement_type: RequirementType = RequirementType.MANDATORY
    condition_description: str = ""
    guidance_note: str = ""
    file_formats: str = "PDF, JPG"
    format_instructions: str = ""
    display_order: int = 0
    is_active: bool = True


@dataclass
class Engagement:
    engagement_id: int = 0
    client_id: int = 0
    service_id: int = 0
    variant_id: Optional[int] = None
    financial_year: str = "2026-2027"
    tax_period: str = "Annual"
    due_date: str = ""
    priority: Priority = Priority.NORMAL
    status: EngagementStatus = EngagementStatus.NOT_STARTED
    assigned_to: int = 0
    reviewer_id: int = 0
    notes: str = ""
    created_by: int = 0
    created_at: str = ""
    updated_at: str = ""
    # Joined helper fields
    client_name: str = ""
    service_name: str = ""
    assigned_name: str = ""
    reviewer_name: str = ""


@dataclass
class EngagementChecklistItem:
    engagement_item_id: int = 0
    engagement_id: int = 0
    source_item_id: int = 0
    category_name: str = ""
    document_name_snapshot: str = ""
    requirement_snapshot: RequirementType = RequirementType.MANDATORY
    applicability_status: ApplicabilityStatus = ApplicabilityStatus.APPLICABLE
    collection_status: DocumentStatus = DocumentStatus.NOT_REQUESTED
    file_formats: str = "PDF, JPG"
    format_instructions: str = ""
    received_date: Optional[str] = None
    verified_by: Optional[int] = None
    waived_by: Optional[int] = None
    waiver_reason: str = ""
    deficiency_reason: str = ""
    internal_remarks: str = ""
    display_order: int = 0

    @property
    def is_exempt(self) -> bool:
        """Return True if item is formally not applicable, waived, or removed from statutory scope."""
        if self.applicability_status == ApplicabilityStatus.NOT_APPLICABLE:
            return True
        if self.collection_status in (DocumentStatus.NOT_APPLICABLE, DocumentStatus.WAIVED_WITH_APPROVAL):
            return True
        if self.internal_remarks:
            rem = self.internal_remarks.lower()
            if "not applicable" in rem or "not required" in rem or "exempt" in rem or "waived" in rem:
                return True
        return False


@dataclass
class DocumentAttachment:
    attachment_id: int = 0
    engagement_item_id: int = 0
    original_filename: str = ""
    stored_filename: str = ""
    storage_relative_path: str = ""
    file_size_bytes: int = 0
    sha256_hash: str = ""
    uploaded_by: int = 0
    uploaded_at: str = ""
    is_archived: bool = False


@dataclass
class FollowUpLog:
    log_id: int = 0
    engagement_id: int = 0
    user_id: int = 0
    communication_mode: str = "Manual Phone Call"
    summary_of_request: str = ""
    client_response: str = ""
    next_follow_up_date: str = ""
    created_at: str = ""
    user_name: str = ""


@dataclass
class ReviewLog:
    review_id: int = 0
    engagement_id: int = 0
    reviewer_id: int = 0
    action: str = "APPROVED"  # APPROVED, RETURNED_FOR_CORRECTION
    observations: str = ""
    created_at: str = ""
    reviewer_name: str = ""


@dataclass
class AuditLog:
    audit_id: int = 0
    actor_id: int = 0
    actor_username: str = ""
    event_type: str = ""
    target_entity: str = ""
    target_id: str = ""
    details: str = ""
    timestamp: str = ""


@dataclass
class ReadinessSummary:
    total_items: int = 0
    mandatory_total: int = 0
    mandatory_accepted: int = 0
    conditional_total: int = 0
    conditional_resolved: int = 0
    conditional_accepted: int = 0
    optional_total: int = 0
    deficient_count: int = 0
    total_files_attached: int = 0
    readiness_percentage: float = 0.0
    collection_percentage: float = 0.0
    is_ready_for_review: bool = False
    blocking_reasons: List[str] = field(default_factory=list)
