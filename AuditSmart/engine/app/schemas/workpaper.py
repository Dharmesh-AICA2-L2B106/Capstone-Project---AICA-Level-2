"""Schemas for /v1/workpaper (prompt 3.6)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StaleOverride(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    kind: Literal["sample", "je_run", "input_vat_run"]
    id: str
    justification: str = Field(max_length=2000)


class WorkpaperCreate(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    engagement_id: str
    wp_ref: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9 ._/-]+$")
    sample_id: str | None = None
    je_run_id: str | None = None
    input_vat_run_id: str | None = None
    reviewer: str | None = Field(default=None, max_length=128)
    stale_overrides: list[StaleOverride] = Field(default_factory=list)


class WorkpaperOut(BaseModel):
    model_config = ConfigDict(extra="allow")
    workpaper_id: str
    wp_ref: str
    status: str
    sha256: str | None
    file_url: str
