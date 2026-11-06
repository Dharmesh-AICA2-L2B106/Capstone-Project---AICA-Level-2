"""Schemas for the FTA rules monitor (prompt 3.9)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

URL_PATTERN = r"^(https://[^\s]+|urn:auditsmart:pending:[a-z0-9-]+)$"


class SourceIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    url: str = Field(pattern=URL_PATTERN, max_length=1024)
    name: str = Field(min_length=3, max_length=255)
    type: Literal["html", "pdf"]
    active: bool = True


class SourcePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    url: str | None = Field(default=None, pattern=URL_PATTERN, max_length=1024)
    name: str | None = Field(default=None, min_length=3, max_length=255)
    type: Literal["html", "pdf"] | None = None
    active: bool | None = None
