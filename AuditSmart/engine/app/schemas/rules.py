"""Schemas for /v1/rules (prompt 3.8)."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RuleProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rule_key: str = Field(min_length=3, max_length=128)
    value: Any
    effective_from: date
    effective_to: date | None = None
    source_url: str | None = Field(default=None, max_length=1024)
    source_ref: str = Field(default="", max_length=2000)
    unit: str = Field(default="", max_length=32)
    comment: str | None = Field(default=None, max_length=2000)


class RuleDecision(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    comment: str = Field(max_length=2000)


class RuleOut(BaseModel):
    model_config = ConfigDict(extra="allow")
    ref: str
    rule_key: str
    version: int
    status: str
