"""Working calendar (SPEC 3.2 / Build Guide 3.5).

The core resolver is brought forward from prompt 3.10 because prompt 3.4 needs
``calendar.resolve(engagement)``. Weekends and holidays are never hard-coded here: every
off-day comes from a layer, and precedence runs from the most specific layer down:

    company exception  >  company work week  >  emirate (week + holidays)  >  federal

Holidays (federal, plus emirate holidays for the client's emirate) apply on top of the
weekly pattern. A company WORKING_DAY exception overrides a holiday, and an EXTRA_HOLIDAY
exception closes a normal day. A date with no work week defined raises CalendarError.

Prompt 3.10 adds the API, Excel import/export (services/calendar_admin.py), Asia/Dubai
conversion helpers and STALE marking on top of these functions.
"""

from __future__ import annotations

import hashlib
import itertools
import json
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

IMPLEMENTED_BY_PROMPT = "3.10"

SEED_PATH = Path(__file__).resolve().parents[2] / "seed_data" / "calendar_seed.json"

LEVELS = ("federal", "emirate", "company")
EXCEPTION_TYPES = ("EXTRA_HOLIDAY", "WORKING_DAY")
DUBAI = ZoneInfo("Asia/Dubai")  # UTC+4, no daylight saving
WORKING, NON_WORKING = "Working", "Non-working"
AFTER_CUTOFF = "Non-working (after half-day cut-off)"


class CalendarError(ValueError):
    """The calendar cannot answer for a date (no work week, overlapping periods ...)."""


def _parse_time(v: str | time) -> time:
    if isinstance(v, time):
        return v
    hh, mm = str(v).split(":")[:2]
    return time(int(hh), int(mm))


@dataclass(frozen=True)
class WorkWeek:
    off_days: frozenset[int]  # ISO weekday 1=Mon .. 7=Sun
    effective_from: date
    effective_to: date | None = None
    half_days: Mapping[int, time] = field(default_factory=dict)  # weekday -> cut-off
    level: str = "federal"
    source: str = ""

    def __post_init__(self) -> None:
        if self.level not in LEVELS:
            raise CalendarError(f"Unknown work-week level '{self.level}'.")
        if any(d < 1 or d > 7 for d in self.off_days) or any(
            d < 1 or d > 7 for d in self.half_days
        ):
            raise CalendarError("Weekdays must be 1 (Monday) to 7 (Sunday).")
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise CalendarError("A work-week period ends before it starts.")
        if set(self.off_days) & set(self.half_days):
            raise CalendarError("A day cannot be both an off day and a half day.")

    def covers(self, d: date) -> bool:
        return self.effective_from <= d and (self.effective_to is None or d <= self.effective_to)

    @classmethod
    def from_dict(cls, item: Mapping[str, Any], level: str | None = None) -> WorkWeek:
        return cls(
            off_days=frozenset(int(x) for x in item.get("off_days", [])),
            half_days={int(k): _parse_time(v) for k, v in (item.get("half_days") or {}).items()},
            effective_from=date.fromisoformat(str(item["effective_from"])),
            effective_to=date.fromisoformat(str(item["effective_to"]))
            if item.get("effective_to")
            else None,
            level=str(level or item.get("level", "federal")),
            source=str(item.get("source", "")),
        )


@dataclass(frozen=True)
class HolidayDay:
    day: date
    name: str
    scope: str = "FEDERAL"  # FEDERAL / EMIRATE
    emirate: str | None = None
    status: str = "confirmed"  # confirmed / provisional

    @property
    def provisional(self) -> bool:
        return self.status.lower() == "provisional"


@dataclass(frozen=True)
class CompanyException:
    day: date
    type: str  # EXTRA_HOLIDAY / WORKING_DAY
    note: str = ""

    def __post_init__(self) -> None:
        if self.type not in EXCEPTION_TYPES:
            raise CalendarError(f"Exception type must be one of {', '.join(EXCEPTION_TYPES)}.")


@dataclass(frozen=True)
class DayStatus:
    day: date
    is_working: bool
    reason: str  # working / half_day / weekend / holiday / company_closure / working_exception
    half_day_cutoff: time | None = None
    source: str = ""  # federal / emirate / company / company_exception
    holiday_name: str | None = None
    provisional: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "date": self.day.isoformat(),
            "is_working": self.is_working,
            "reason": self.reason,
            "half_day_cutoff": self.half_day_cutoff.strftime("%H:%M")
            if self.half_day_cutoff
            else None,
            "source": self.source,
            "holiday_name": self.holiday_name,
            "provisional": self.provisional,
        }


def check_no_overlap(weeks: Iterable[WorkWeek]) -> None:
    """Periods at the same level must not overlap (Build Guide 3.5)."""
    by_level: dict[str, list[WorkWeek]] = {}
    for w in weeks:
        by_level.setdefault(w.level, []).append(w)
    for level, items in by_level.items():
        items.sort(key=lambda w: w.effective_from)
        for a, b in itertools.pairwise(items):
            if a.effective_to is None or a.effective_to >= b.effective_from:
                raise CalendarError(
                    f"Overlapping {level} work-week periods starting "
                    f"{a.effective_from.isoformat()} and {b.effective_from.isoformat()}."
                )


@dataclass(frozen=True)
class CalendarProfile:
    """All layers that apply to one client."""

    emirate: str | None = None
    weeks: tuple[WorkWeek, ...] = ()
    holidays: tuple[HolidayDay, ...] = ()
    exceptions: tuple[CompanyException, ...] = ()
    name: str = ""

    def __post_init__(self) -> None:
        check_no_overlap(self.weeks)
        seen: set[date] = set()
        for e in self.exceptions:
            if e.day in seen:
                raise CalendarError(f"Two company exceptions on {e.day.isoformat()}.")
            seen.add(e.day)

    def week_for(self, d: date) -> WorkWeek:
        for level in ("company", "emirate", "federal"):
            for w in self.weeks:
                if w.level == level and w.covers(d):
                    return w
        raise CalendarError(
            f"No work week is defined for {d.isoformat()}. Add the company or emirate work "
            "week in the Working Calendar before running date-based tests."
        )

    def holiday_on(self, d: date) -> HolidayDay | None:
        emirate_hit = federal_hit = None
        for h in self.holidays:
            if h.day != d:
                continue
            if h.scope.upper() == "EMIRATE":
                if self.emirate and h.emirate and h.emirate.lower() == self.emirate.lower():
                    emirate_hit = h
            else:
                federal_hit = h
        return emirate_hit or federal_hit


def day_status(profile: CalendarProfile, d: date) -> DayStatus:
    exc = next((e for e in profile.exceptions if e.day == d), None)
    if exc is not None and exc.type == "EXTRA_HOLIDAY":
        return DayStatus(
            d, False, "company_closure", source="company_exception", holiday_name=exc.note or None
        )
    week = profile.week_for(d)
    if exc is not None:  # WORKING_DAY beats holidays and weekends
        return DayStatus(d, True, "working_exception", source="company_exception")
    hol = profile.holiday_on(d)
    if hol is not None:
        return DayStatus(
            d,
            False,
            "holiday",
            source=hol.scope.lower(),
            holiday_name=hol.name,
            provisional=hol.provisional,
        )
    wd = d.isoweekday()
    if wd in week.off_days:
        return DayStatus(d, False, "weekend", source=week.level)
    if wd in week.half_days:
        return DayStatus(d, True, "half_day", half_day_cutoff=week.half_days[wd], source=week.level)
    return DayStatus(d, True, "working", source=week.level)


def resolve(profile: CalendarProfile, start: date, end: date) -> list[DayStatus]:
    """One DayStatus per date from ``start`` to ``end`` inclusive."""
    if end < start:
        raise CalendarError("The end date is before the start date.")
    return [day_status(profile, start + timedelta(days=i)) for i in range((end - start).days + 1)]


def to_dubai(value: datetime) -> datetime:
    """Asia/Dubai wall time.  Naive values are taken as already local (ERP exports in the
    UAE carry local time without an offset); aware values are converted."""
    if value.tzinfo is None:
        return value.replace(tzinfo=DUBAI)
    return value.astimezone(DUBAI)


def posting_label(profile: CalendarProfile, when: datetime | date,
                  at: time | None = None) -> str:
    """Golden Calendar-sheet wording for a posting: Working / Non-working /
    Non-working (after half-day cut-off).  Times are compared in Asia/Dubai."""
    if isinstance(when, datetime):
        local = to_dubai(when)
        d, at = local.date(), local.time().replace(tzinfo=None)
    else:
        d = when
    st = day_status(profile, d)
    if not st.is_working:
        return NON_WORKING
    if st.half_day_cutoff is not None and at is not None and at > st.half_day_cutoff:
        return AFTER_CUTOFF
    return WORKING


def calendar_hash(days: Iterable[DayStatus]) -> str:
    payload = json.dumps([d.as_dict() for d in days], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ResolvedCalendar:
    """Calendar resolved for a date range, with lazy look-ups outside it."""

    def __init__(self, profile: CalendarProfile, start: date, end: date) -> None:
        self.profile = profile
        self.start, self.end = start, end
        self.days = {s.day: s for s in resolve(profile, start, end)}
        self.hash = calendar_hash(self.days.values())

    def status(self, d: date) -> DayStatus:
        if d not in self.days:
            self.days[d] = day_status(self.profile, d)
        return self.days[d]

    def summary(self) -> dict[str, Any]:
        inside = [s for s in self.days.values() if self.start <= s.day <= self.end]
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "hash": self.hash,
            "emirate": self.profile.emirate,
            "non_working_days": sum(not s.is_working for s in inside),
            "half_days": sum(s.reason == "half_day" for s in inside),
            "provisional_holidays": sorted(s.day.isoformat() for s in inside if s.provisional),
            "layers": {"work_weeks": sorted({w.level for w in self.profile.weeks}),
                       "holidays": sorted({h.scope for h in self.profile.holidays}),
                       "company_exceptions": len(self.profile.exceptions),
                       "day_sources": dict(sorted(Counter(s.source for s in inside).items()))},
            "pending_verification": True,
        }


# ------------------------------------------------------------------ seed + database loaders
@lru_cache
def _seed(path: str = str(SEED_PATH)) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(Path(path).read_text(encoding="utf-8"))
    return data


def seed_weeks() -> tuple[WorkWeek, ...]:
    return tuple(WorkWeek.from_dict(w) for w in _seed()["work_weeks"])


def seed_holidays() -> tuple[HolidayDay, ...]:
    return tuple(
        HolidayDay(
            date.fromisoformat(h["date"]),
            h["name"],
            h.get("scope", "FEDERAL"),
            h.get("emirate"),
            h.get("status", "confirmed"),
        )
        for h in _seed()["holidays"]
    )


def load_profile(client_id: str, session: Any = None,
                 emirate: str | None = None) -> CalendarProfile:
    """Build a client's profile from the calendar tables (seed file as federal fallback).

    ``emirate`` overrides the client's emirate (what-if / resolve(client, emirate, ...))."""
    from contextlib import nullcontext

    from sqlalchemy import select

    from app.core.db import session_factory
    from app.models import Client, CompanyWorkweek, EmirateProfile, Holiday
    from app.models import CompanyException as ExcRow

    with nullcontext(session) if session is not None else session_factory()() as s:
        cl = s.get(Client, client_id)
        if cl is None:
            raise CalendarError("Client not found for the calendar.")
        emirate = emirate or cl.emirate
        weeks: list[WorkWeek] = []
        fed_rows = s.scalars(
            select(EmirateProfile).where(EmirateProfile.emirate == "FEDERAL")
        ).all()
        em_rows = (
            s.scalars(select(EmirateProfile).where(EmirateProfile.emirate == emirate)).all()
            if emirate
            else []
        )
        for lvl, rows in (("federal", fed_rows), ("emirate", em_rows)):
            weeks += [
                WorkWeek(
                    frozenset(r.off_days),
                    r.effective_from,
                    r.effective_to,
                    {int(k): _parse_time(v) for k, v in (r.half_days or {}).items()},
                    level=lvl,
                    source=f"emirate_profiles:{r.id}",
                )
                for r in rows
            ]
        if not fed_rows:
            weeks += list(seed_weeks())
        weeks += [
            WorkWeek(
                frozenset(r.off_days),
                r.effective_from,
                r.effective_to,
                {int(k): _parse_time(v) for k, v in (r.half_days or {}).items()},
                level="company",
                source=f"company_workweeks:{r.id}",
            )
            for r in s.scalars(
                select(CompanyWorkweek).where(CompanyWorkweek.client_id == client_id)
            ).all()
        ]
        hol_rows = s.scalars(select(Holiday)).all()
        holidays = [HolidayDay(h.date, h.name, h.scope, h.emirate, h.status) for h in hol_rows]
        if not any(h.scope.upper() == "FEDERAL" for h in holidays):
            holidays += list(seed_holidays())
        excs = [
            CompanyException(r.date, r.type, r.note or "")
            for r in s.scalars(select(ExcRow).where(ExcRow.client_id == client_id)).all()
        ]
    return CalendarProfile(
        emirate=emirate,
        weeks=tuple(weeks),
        holidays=tuple(holidays),
        exceptions=tuple(excs),
        name=client_id,
    )


def resolve_client(client_id: str, emirate: str | None, start: date, end: date,
                   session: Any = None) -> ResolvedCalendar:
    """``resolve(client, emirate, start, end)`` of the Build Guide."""
    return ResolvedCalendar(load_profile(client_id, session, emirate), start, end)


def resolve_engagement(engagement_id: str, start: date, end: date,
                       session: Any = None) -> ResolvedCalendar:
    from contextlib import nullcontext

    from app.core.db import session_factory
    from app.models import Engagement

    with nullcontext(session) if session is not None else session_factory()() as s:
        eng = s.get(Engagement, engagement_id)
        if eng is None:
            raise CalendarError("Engagement not found for the calendar.")
        client_id = eng.client_id
    return ResolvedCalendar(load_profile(client_id, session), start, end)
