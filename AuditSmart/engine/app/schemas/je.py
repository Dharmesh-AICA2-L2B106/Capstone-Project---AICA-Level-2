"""Request/response models for JE tests and Benford (prompt 3.4)."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.sampling import Money, Pct

TestCode = Annotated[str, Field(min_length=1, max_length=64)]


class JeParamsIn(BaseModel):
    """Optional overrides; anything omitted comes from the Rules Library (je.*)."""

    model_config = ConfigDict(strict=True, extra="forbid")

    round_multiple: Money | None = None
    round_min: Money | None = None
    period_end_days: int | None = Field(default=None, ge=0, le=60)
    rare_user_max_pct: Pct | None = None
    vague_keywords: list[str] | None = None
    account_pair_min_count: int | None = Field(default=None, ge=1, le=1000)
    score_test: int | None = Field(default=None, ge=1, le=20)
    score_judgement: int | None = Field(default=None, ge=1, le=20)
    judgement_min_items: int | None = Field(default=None, ge=0, le=10_000)
    manual_voucher_prefixes: list[str] | None = None
    sensitive_account_types: list[str] | None = None
    sensitive_account_codes: list[str] | None = None
    senior_users: list[str] | None = None
    large_amount: Money | None = None
    tests: list[TestCode] | None = None


class JeRunCreate(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    dataset_id: str
    parameters: JeParamsIn = Field(default_factory=JeParamsIn)


class JeRunAccepted(BaseModel):
    je_run_id: str
    job_id: str
    status_url: str
    result_url: str


class JeRunOut(BaseModel):
    model_config = ConfigDict(extra="allow")

    je_run_id: str
    status: str
    job_id: str | None = None
    dataset_id: str
    engagement_id: str


class BenfordCreate(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    dataset_id: str
    account_types: list[str] = Field(default_factory=list)
    min_amount: Money | None = None


class BenfordOut(BaseModel):
    model_config = ConfigDict(extra="allow")

    dataset_id: str
    n: int
    mad: float
    conclusion: str
    chart: list[dict[str, Any]]
