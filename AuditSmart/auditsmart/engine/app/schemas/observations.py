"""Schemas for /v1/ai/observation and /v1/observations (prompt 3.7)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.services.ai_gateway import ObservationDraft


class ObservationCreate(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    sample_item_id: str
    failed_attribute: str = Field(min_length=1, max_length=200)
    test: str = Field(default="Test of details", min_length=1, max_length=200)
    remark: str | None = Field(default=None, max_length=2000)
    rule_keys: list[str] = Field(default_factory=list, max_length=20)


class ObservationReview(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    text: ObservationDraft | None = None


class ObservationOut(BaseModel):
    model_config = ConfigDict(extra="allow")
    observation_id: str
    ai_generated: bool
