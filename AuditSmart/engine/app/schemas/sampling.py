"""Request/response models for POST /v1/sample (prompt 3.3)."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# Money is sent as a JSON string ("280000.00") or integer; floats are accepted but discouraged.
Money = Annotated[Decimal, Field(strict=False, gt=0, max_digits=24, decimal_places=6)]
Pct = Annotated[Decimal, Field(strict=False, ge=0, le=1)]


class SampleCreate(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    dataset_id: str
    method: Literal["mus", "random", "systematic", "stratified", "key_items_mus"] = "mus"
    basis: Literal["debit", "credit", "signed", "absolute"] = "debit"
    account_types: list[str] = Field(default_factory=list)
    account_codes: list[str] = Field(default_factory=list)
    confidence: Literal["80", "90", "95", "99"] = "95"
    tolerable_misstatement: Money | None = None
    expected_misstatement_pct: Pct | None = None
    size_formula: Literal["firm", "guide"] = "firm"
    sample_size: int | None = Field(default=None, ge=1, le=100_000)
    key_item_threshold: Money | None = None
    strata_boundaries: list[Money] | None = None
    num_strata: int | None = Field(default=None, ge=1, le=20)
    seed: int | None = Field(default=None, ge=0, le=2**31 - 1)


class SampleOut(BaseModel):
    """The stored result. Money values are strings with full precision."""

    model_config = ConfigDict(extra="allow")

    sample_id: str
    dataset_id: str
    engagement_id: str
    method: str
    status: str
    parameters: dict[str, Any]
    cf_value: str | None
    cf_rule_version: str | None
    formula_text: str | None
    n_required: int | None
    sample_size: int
    seed: int
    random_start: str | None
    interval: str | None
    basic_precision: str | None
    population: dict[str, Any]
    top_stratum: dict[str, Any]
    key_items: dict[str, Any]
    credit_lines_excluded: dict[str, Any]
    strata: list[dict[str, Any]]
    items: list[dict[str, Any]]
    warnings: list[str]
    rationale: str
    engine_version: str
    dataset_hash: str | None
    rule_versions_used: dict[str, Any]
    rules_pending_verification: bool
