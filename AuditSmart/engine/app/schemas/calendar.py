"""Calendar API bodies (prompt 3.10)."""

from __future__ import annotations

import datetime as dt
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"


class WorkWeekIn(BaseModel):
    model_config = ConfigDict(extra="forbid")  # dates arrive as ISO strings
    off_days: list[int] = Field(max_length=7)
    half_days: dict[Literal["1", "2", "3", "4", "5", "6", "7"],
                    str] = Field(default_factory=dict)
    effective_from: dt.date
    effective_to: dt.date | None = None

    @field_validator("half_days")
    @classmethod
    def _times(cls, v: dict[str, str]) -> dict[str, str]:
        for t in v.values():
            if not re.match(_HHMM, t):
                raise ValueError("half-day cut-offs must be HH:MM (Asia/Dubai)")
        return v

    @field_validator("off_days")
    @classmethod
    def _days(cls, v: list[int]) -> list[int]:
        if any(d < 1 or d > 7 for d in v) or len(set(v)) != len(v):
            raise ValueError("off days are distinct ISO weekdays 1 (Mon) .. 7 (Sun)")
        return sorted(v)

    def halves(self) -> dict[str, str]:
        return {str(k): v for k, v in self.half_days.items()}


class EmirateWeekIn(WorkWeekIn):
    emirate: str = Field(min_length=1, max_length=32)


class ExceptionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")  # dates arrive as ISO strings
    date: dt.date
    type: Literal["EXTRA_HOLIDAY", "WORKING_DAY"]
    note: str | None = Field(default=None, max_length=500)


class HolidayIn(BaseModel):
    model_config = ConfigDict(extra="forbid")  # dates arrive as ISO strings
    date: dt.date
    name: str = Field(min_length=1, max_length=255)
    scope: Literal["FEDERAL", "EMIRATE"] = "FEDERAL"
    emirate: str | None = Field(default=None, max_length=32)
    status: Literal["confirmed", "provisional"] = "confirmed"


class HolidayPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")  # dates arrive as ISO strings
    status: Literal["confirmed", "provisional"]

