"""Schemas for /v1/vat-check and /v1/evaluate (prompt 3.5)."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.sampling import Money

Side = Literal["output", "input"]

# audited values may be zero or negative (e.g. a fictitious invoice audited at nil)
AuditedMoney = Annotated[Decimal, Field(strict=False, max_digits=24, decimal_places=6)]


class VatCheckCreate(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    dataset_id: str
    sides: list[Side] = Field(default_factory=lambda: list[Side](["output", "input"]))


class VatCheckOut(BaseModel):
    model_config = ConfigDict(extra="allow")
    dataset_id: str
    exceptions_count: int


class AuditedItem(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    line_ref: str
    audited_value: AuditedMoney
    remarks: str | None = Field(default=None, max_length=2000)
    evidence_ref: str | None = Field(default=None, max_length=128)


class EvaluateCreate(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    sample_id: str
    method: Literal["mus", "ratio"] | None = None
    tolerable_misstatement: Money | None = None
    items: list[AuditedItem] = Field(default_factory=list)


class EvaluationOut(BaseModel):
    model_config = ConfigDict(extra="allow")
    sample_id: str
    method: str
    conclusion: str
