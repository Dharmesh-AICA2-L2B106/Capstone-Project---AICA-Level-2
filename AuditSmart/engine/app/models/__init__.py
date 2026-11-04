"""SQLAlchemy models for every Appendix A table (portable: JSON instead of jsonb / int[]).

Additions beyond Appendix A are marked ``# +`` and listed in SPEC.md (Stage 3 changes).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

MONEY = Numeric(20, 2)


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class Firm(Base):  # + multi-firm (D42): the audit firm (tenant) that owns clients
    __tablename__ = "firms"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # = the token's firm claim
    name: Mapped[str] = mapped_column(String(255))
    # Tighten-only: True makes this firm resolve approved rules only, even while the
    # deployment-wide RULES_ALLOW_PENDING is true (D44).
    require_approved_rules: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=_now)


class Client(Base):
    __tablename__ = "clients"
    # D52: client codes are unique per firm (two firms may both use "C001"); was global.
    __table_args__ = (UniqueConstraint("firm_id", "client_code", name="uq_clients_firm_code"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    client_code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(255))
    emirate: Mapped[str] = mapped_column(String(32))
    entity_type: Mapped[str | None] = mapped_column(String(64))
    firm_id: Mapped[str | None] = mapped_column(ForeignKey("firms.id"), index=True)  # + D42


class Engagement(Base):
    __tablename__ = "engagements"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"))
    fye: Mapped[date] = mapped_column(Date)
    framework: Mapped[str | None] = mapped_column(String(64))
    materiality: Mapped[Decimal | None] = mapped_column(MONEY)
    perf_materiality: Mapped[Decimal | None] = mapped_column(MONEY)
    trivial: Mapped[Decimal | None] = mapped_column(MONEY)
    status: Mapped[str] = mapped_column(String(32), default="planning")


class EngagementMember(Base):
    __tablename__ = "engagement_members"
    engagement_id: Mapped[str] = mapped_column(ForeignKey("engagements.id"), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    role: Mapped[str] = mapped_column(String(32))


class Dataset(Base):
    __tablename__ = "datasets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    engagement_id: Mapped[str] = mapped_column(ForeignKey("engagements.id"))
    file_name: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str | None] = mapped_column(String(64))
    rows: Mapped[int | None] = mapped_column(Integer)
    total_dr: Mapped[Decimal | None] = mapped_column(MONEY)
    total_cr: Mapped[Decimal | None] = mapped_column(MONEY)
    storage_ref: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(32), default="uploading")
    kind: Mapped[str] = mapped_column(String(8), default="GL")  # + GL / TB
    size_bytes: Mapped[int | None] = mapped_column(Integer)  # +
    chunks_received: Mapped[int] = mapped_column(Integer, default=0)  # +
    parquet_ref: Mapped[str | None] = mapped_column(String(512))  # + Parquet cache
    mapping: Mapped[dict[str, Any] | None] = mapped_column(JSON)  # + header mapping used
    profile: Mapped[dict[str, Any] | None] = mapped_column(JSON)  # + counts, date range
    created_by: Mapped[str | None] = mapped_column(String(128))  # +
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)  # +


class ValidationError(Base):
    __tablename__ = "validation_errors"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)  # +
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), index=True)
    severity: Mapped[str] = mapped_column(String(16))
    code: Mapped[str] = mapped_column(String(64))  # +
    field: Mapped[str | None] = mapped_column(String(64))
    rows: Mapped[list[int]] = mapped_column(JSON)  # first 50 data-row numbers
    row_count: Mapped[int] = mapped_column(Integer, default=0)  # +
    message: Mapped[str] = mapped_column(Text)
    guidance: Mapped[str] = mapped_column(Text)


class Sample(Base):
    __tablename__ = "samples"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    engagement_id: Mapped[str] = mapped_column(ForeignKey("engagements.id"))
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"))
    method: Mapped[str] = mapped_column(String(32))
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON)
    cf_value: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    formula_text: Mapped[str | None] = mapped_column(Text)
    seed: Mapped[int | None] = mapped_column(Integer)
    file_hash: Mapped[str | None] = mapped_column(String(64))
    rule_versions_used: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    engine_version: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="current")
    created_by: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)  # + full result (3.3)


class SampleItem(Base):
    __tablename__ = "sample_items"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    sample_id: Mapped[str] = mapped_column(ForeignKey("samples.id"), index=True)
    line_ref: Mapped[str] = mapped_column(String(64))
    book_value: Mapped[Decimal] = mapped_column(MONEY)
    top_stratum: Mapped[bool] = mapped_column(Boolean, default=False)
    attributes: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    audited_value: Mapped[Decimal | None] = mapped_column(MONEY)
    misstatement: Mapped[Decimal | None] = mapped_column(MONEY)
    remarks: Mapped[str | None] = mapped_column(Text)
    evidence_ref: Mapped[str | None] = mapped_column(String(128))


class JeRun(Base):
    __tablename__ = "je_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    engagement_id: Mapped[str] = mapped_column(ForeignKey("engagements.id"))
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"))
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON)
    calendar_hash: Mapped[str | None] = mapped_column(String(64))
    rule_versions_used: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    engine_version: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="current")
    job_id: Mapped[str | None] = mapped_column(String(36))  # +
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)  # + summary, tests, benford
    created_by: Mapped[str | None] = mapped_column(String(128))  # +
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),  # +
        default=_now,
    )


class JeFlag(Base):
    __tablename__ = "je_flags"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)  # +
    je_run_id: Mapped[str] = mapped_column(ForeignKey("je_runs.id"), index=True)
    line_ref: Mapped[str] = mapped_column(String(64))
    flags: Mapped[list[str]] = mapped_column(JSON)
    risk_score: Mapped[int] = mapped_column(Integer)


class InputVatRun(Base):
    __tablename__ = "input_vat_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    engagement_id: Mapped[str] = mapped_column(ForeignKey("engagements.id"))
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"))
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON)
    rule_versions_used: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    engine_version: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="current")
    job_id: Mapped[str | None] = mapped_column(String(36))  # + 3.12
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)  # + 3.12
    created_by: Mapped[str | None] = mapped_column(String(128))  # + 3.12
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),  # + 3.12
        default=_now,
    )


class SupplierRegister(Base):
    __tablename__ = "supplier_register"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    engagement_id: Mapped[str] = mapped_column(ForeignKey("engagements.id"))
    supplier_id: Mapped[str] = mapped_column(String(64))
    supplier_name: Mapped[str | None] = mapped_column(String(255))
    trn: Mapped[str | None] = mapped_column(String(32))
    verified_on: Mapped[date | None] = mapped_column(Date)
    evidence_ref: Mapped[str | None] = mapped_column(String(128))
    risk_indicators: Mapped[list[str] | None] = mapped_column(JSON)
    explanation: Mapped[str | None] = mapped_column(Text)
    bank_evidence_ref: Mapped[str | None] = mapped_column(String(128))


class ExpenseMapping(Base):
    __tablename__ = "expense_mapping"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    engagement_id: Mapped[str] = mapped_column(ForeignKey("engagements.id"))
    account_code: Mapped[str] = mapped_column(String(32))
    category: Mapped[str] = mapped_column(String(64))


class Observation(Base):
    __tablename__ = "observations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    sample_item_id: Mapped[str] = mapped_column(ForeignKey("sample_items.id"))
    text: Mapped[dict[str, Any]] = mapped_column(JSON)
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=False)
    prompt_version: Mapped[str | None] = mapped_column(String(32))
    model: Mapped[str | None] = mapped_column(String(64))
    reviewed_by: Mapped[str | None] = mapped_column(String(128))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Workpaper(Base):
    __tablename__ = "workpapers"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    engagement_id: Mapped[str] = mapped_column(ForeignKey("engagements.id"))
    wp_ref: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="draft")
    preparer: Mapped[str | None] = mapped_column(String(128))
    reviewer: Mapped[str | None] = mapped_column(String(128))
    prepared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tool_version: Mapped[str | None] = mapped_column(String(32))
    file_ref: Mapped[str | None] = mapped_column(String(512))  # + stored .xlsx (3.6)
    sha256: Mapped[str | None] = mapped_column(String(64))  # +
    manifest: Mapped[dict[str, Any] | None] = mapped_column(JSON)  # + included results
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                        default=_now)  # +
    __table_args__ = (
        CheckConstraint("status in ('draft','prepared','reviewed','locked')", name="ck_wp_status"),
    )


class RuleVersion(Base):
    __tablename__ = "rule_versions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    rule_key: Mapped[str] = mapped_column(String(128), index=True)
    value: Mapped[Any] = mapped_column(JSON)
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    source_url: Mapped[str | None] = mapped_column(String(1024))
    source_doc_hash: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="pending_verification")
    proposed_by: Mapped[str | None] = mapped_column(String(128))
    approved_by: Mapped[str | None] = mapped_column(String(128))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    comment: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)  # + rule_key@vN (3.8)
    domain: Mapped[str | None] = mapped_column(String(16))  # + VAT, INPUT_VAT, CT, ... (3.8)
    unit: Mapped[str | None] = mapped_column(String(128))  # + (3.8); widened 0009 (D49)
    source_ref: Mapped[str | None] = mapped_column(Text)  # + citation text (3.8)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),  # +
        default=_now,
    )
    # + D42 multi-firm: NULL firm_id = shared default (baseline); set = that firm's override;
    # engagement_id additionally narrows the override to one engagement of the firm.
    firm_id: Mapped[str | None] = mapped_column(ForeignKey("firms.id"), index=True)
    engagement_id: Mapped[str | None] = mapped_column(ForeignKey("engagements.id"), index=True)
    based_on_id: Mapped[str | None] = mapped_column(String(36))  # default version overridden
    # "no overlapping approved periods per rule_key" is enforced in the rules service (3.8);
    # PostgreSQL adds an exclusion constraint in a later migration.
    __table_args__ = (
        CheckConstraint(
            "status in ('pending_verification','proposed','approved','rejected','superseded')",
            name="ck_rule_status",
        ),
    )


class FirmRuleApproval(Base):  # + D42: a firm partner's sign-off of a shared default version
    """Insert-only: one row per (firm, default rule version). The shared row is never edited,
    so one firm's approval cannot change what another firm resolves."""

    __tablename__ = "firm_rule_approvals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    firm_id: Mapped[str] = mapped_column(ForeignKey("firms.id"), index=True)
    rule_version_id: Mapped[str] = mapped_column(ForeignKey("rule_versions.id"))
    rule_key: Mapped[str] = mapped_column(String(128))
    approved_by: Mapped[str] = mapped_column(String(128))
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    comment: Mapped[str] = mapped_column(Text)
    __table_args__ = (
        UniqueConstraint("firm_id", "rule_version_id", name="uq_firm_rule_approval"),
    )


class WatchedSource(Base):
    __tablename__ = "watched_sources"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    url: Mapped[str] = mapped_column(String(1024), unique=True)
    type: Mapped[str] = mapped_column(String(32))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_hash: Mapped[str | None] = mapped_column(String(64))
    last_checked: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    name: Mapped[str | None] = mapped_column(String(255))  # + (3.9)
    last_error: Mapped[str | None] = mapped_column(Text)  # + (3.9)
    last_links: Mapped[list[str] | None] = mapped_column(JSON)  # + document links seen (3.9)


class UpdateAlert(Base):
    __tablename__ = "update_alerts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    source_id: Mapped[str | None] = mapped_column(ForeignKey("watched_sources.id"))
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    summary: Mapped[str | None] = mapped_column(Text)
    proposal_ids: Mapped[list[str] | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default="open")
    kind: Mapped[str] = mapped_column(String(16), default="change")  # + change|failure|upload
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON)  # + links, hash, snapshot


class Holiday(Base):
    __tablename__ = "holidays"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date)
    name: Mapped[str] = mapped_column(String(128))
    scope: Mapped[str] = mapped_column(String(16))  # FEDERAL / EMIRATE
    emirate: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="provisional")
    __table_args__ = (UniqueConstraint("date", "scope", "emirate", name="uq_holiday"),)


class EmirateProfile(Base):
    __tablename__ = "emirate_profiles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    emirate: Mapped[str] = mapped_column(String(32))
    off_days: Mapped[list[int]] = mapped_column(JSON)  # ISO weekday 1=Mon .. 7=Sun
    half_days: Mapped[dict[str, str] | None] = mapped_column(JSON)  # + {"5": "12:00"}
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)


class CompanyWorkweek(Base):
    __tablename__ = "company_workweeks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"))
    off_days: Mapped[list[int]] = mapped_column(JSON)
    half_days: Mapped[dict[str, str]] = mapped_column(JSON)  # {"5": "12:00"}
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)


class CompanyException(Base):
    __tablename__ = "company_exceptions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"))
    date: Mapped[date] = mapped_column(Date)
    type: Mapped[str] = mapped_column(String(16))  # EXTRA_HOLIDAY / WORKING_DAY
    note: Mapped[str | None] = mapped_column(Text)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    type: Mapped[str] = mapped_column(String(32))
    engagement_id: Mapped[str | None] = mapped_column(ForeignKey("engagements.id"))
    status: Mapped[str] = mapped_column(String(16), default="queued")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    result_ref: Mapped[str | None] = mapped_column(String(512))
    created_by: Mapped[str | None] = mapped_column(String(128))  # +
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint(
            "status in ('queued','running','succeeded','failed','cancelled')", name="ck_job_status"
        ),
    )


class AuditLog(Base):
    """Insert-only (enforced in the data layer and by DB grants in production)."""

    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str | None] = mapped_column(String(128))
    action: Mapped[str] = mapped_column(String(32))
    entity: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    old: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    new: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


APPENDIX_A_TABLES = (
    "clients",
    "engagements",
    "engagement_members",
    "datasets",
    "validation_errors",
    "samples",
    "sample_items",
    "je_runs",
    "je_flags",
    "input_vat_runs",
    "supplier_register",
    "expense_mapping",
    "observations",
    "workpapers",
    "rule_versions",
    "watched_sources",
    "update_alerts",
    "holidays",
    "emirate_profiles",
    "company_workweeks",
    "company_exceptions",
    "jobs",
    "audit_log",
)

# Additions beyond Appendix A for multi-firm use (D42, migration 0008).
MULTI_FIRM_TABLES = ("firms", "firm_rule_approvals")
