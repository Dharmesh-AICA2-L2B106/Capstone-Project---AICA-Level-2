"""Schemas for /v1/firm and /v1/firms (multi-firm rule approval, D42)."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FirmCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=2, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    name: str = Field(min_length=2, max_length=255)
    require_approved_rules: bool = False


class FirmSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    require_approved_rules: bool
    comment: str = Field(max_length=2000)


class FirmRuleApprove(BaseModel):
    model_config = ConfigDict(extra="forbid")
    comment: str = Field(max_length=2000)
    version_id: str | None = Field(default=None, max_length=36)
    on: date | None = None


class FirmRuleOverride(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: Any
    effective_from: date
    effective_to: date | None = None
    engagement_id: str | None = Field(default=None, max_length=36)
    source_url: str | None = Field(default=None, max_length=1024)
    source_ref: str = Field(default="", max_length=2000)
    unit: str = Field(default="", max_length=32)
    comment: str = Field(max_length=2000)


class FirmRuleReject(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version_id: str = Field(max_length=36)
    comment: str = Field(max_length=2000)
