"""Request/response models for the input-VAT checks (prompt 3.12)."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

Code = Annotated[str, Field(min_length=1, max_length=32)]


class InputVatCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str
    effective_date_override: date | None = Field(
        default=None, description="TEST-ONLY (D4): replaces the rule effective date")


class InputVatAccepted(BaseModel):
    input_vat_run_id: str
    job_id: str
    status_url: str
    result_url: str


class MappingItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_code: Code
    category: Annotated[str, Field(min_length=1, max_length=64)]


class MappingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: Annotated[list[MappingItem], Field(max_length=2000)]
