"""Schemas for the engagement sync endpoints (PUT/GET /v1/engagements/{id}, D50-D55).

The front end (Lovable) owns clients, engagements and teams in its own database and copies
them to the engine with one idempotent PUT. Money fields are Decimal (never float maths).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.security import normalise_roles

ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]*$"
Money = Annotated[Decimal, Field(ge=0, max_digits=20, decimal_places=2)]


class ClientSync(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=36, pattern=ID_PATTERN)
    client_code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=255)
    emirate: str = Field(min_length=2, max_length=32)
    entity_type: str | None = Field(default=None, max_length=64)


class MemberSync(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._@:|-]+$")
    role: str = Field(min_length=1, max_length=32)

    @field_validator("role")
    @classmethod
    def _role(cls, v: str) -> str:
        roles = normalise_roles(v)
        if len(roles) != 1:
            raise ValueError("role must be one of Admin, Partner, Manager, Senior, Staff, "
                             "TaxPartner")
        return next(iter(roles))


class EngagementSync(BaseModel):
    """Full engagement as the front end holds it. ``members`` replaces the whole team.

    On update, optional fields that are left out keep their current value; send ``null``
    to clear one.
    """

    model_config = ConfigDict(extra="forbid")
    client: ClientSync
    fye: date
    framework: str | None = Field(default=None, max_length=64)
    materiality: Money | None = None
    perf_materiality: Money | None = None
    trivial: Money | None = None
    status: str | None = Field(default=None, min_length=1, max_length=32)
    members: list[MemberSync] = Field(max_length=200)

    @model_validator(mode="after")
    def _check(self) -> EngagementSync:
        ids = [m.user_id for m in self.members]
        if len(ids) != len(set(ids)):
            raise ValueError("members: each user_id may appear only once")
        if not any(m.role in ("Manager", "Partner") for m in self.members):
            raise ValueError("members: the team needs at least one Manager or Partner")
        m, pm, tr = self.materiality, self.perf_materiality, self.trivial
        if m is not None and pm is not None and pm > m:
            raise ValueError("perf_materiality cannot be more than materiality")
        if m is not None and tr is not None and tr > m:
            raise ValueError("trivial cannot be more than materiality")
        return self


class EngagementOut(BaseModel):
    created: bool | None = None
    engagement: dict[str, Any]
    client: dict[str, Any]
    members: list[dict[str, str]]
    stale: list[dict[str, Any]] = Field(default_factory=list)
