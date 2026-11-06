"""Prompt 3.10 against golden_results.xlsx sheet "Calendar" (12 cases x profiles P1-P4)
and the Fri/Sat -> Sat/Sun change in fy2021_2022.csv (answer key, 60 planted lines)."""

from __future__ import annotations

import csv
from datetime import UTC, date, datetime, time

import pytest

from app.services import calendar as c
from tests.helpers import DATA, answer_key, golden

START = date(2000, 1, 1)
CHANGE = date(2022, 1, 1)


def _holidays() -> tuple[c.HolidayDay, ...]:
    ws = golden()["Calendar"]
    out = []
    for d, name in ws.iter_rows(min_row=6, max_row=40, min_col=16, max_col=17,
                                values_only=True):
        if d is not None:
            out.append(c.HolidayDay(d.date() if isinstance(d, datetime) else d, str(name)))
    return tuple(out)


def _profiles() -> dict[str, c.CalendarProfile]:
    hol = _holidays()
    ws = golden()["Calendar"]
    cutoff, change = ws["B3"].value, ws["D3"].value
    assert cutoff == time(12, 0) and change.date() == CHANGE
    w = c.WorkWeek
    return {
        "P1": c.CalendarProfile(weeks=(w(frozenset({5}), START),), holidays=hol),
        "P2": c.CalendarProfile(weeks=(w(frozenset({6, 7}), START, None, {5: cutoff}),),
                                holidays=hol),
        "P3": c.CalendarProfile(weeks=(w(frozenset({5, 6, 7}), START),), holidays=hol),
        "P4": c.CalendarProfile(weeks=(w(frozenset({5, 6}), START, date(2021, 12, 31)),
                                       w(frozenset({6, 7}), CHANGE)), holidays=hol),
    }


def _cases() -> list[tuple[datetime, dict[str, str]]]:
    rows = golden()["Calendar"].iter_rows(min_row=6, max_row=17, max_col=8, values_only=True)
    return [(datetime.combine(r[0].date(), r[1]), dict(zip(("P1", "P2", "P3", "P4"), r[4:8],
                                                           strict=True))) for r in rows]


def test_golden_sheet_has_12_cases_and_12_holidays() -> None:
    assert len(_cases()) == 12 and len(_holidays()) == 12
    seed = {h.day for h in c.seed_holidays() if h.day.year == 2025}
    assert {h.day for h in _holidays()} <= seed  # the seed carries the golden 2025 list
    assert golden()["Calendar"]["B19"].value == "OK"


@pytest.mark.parametrize("profile", ["P1", "P2", "P3", "P4"])
def test_golden_calendar_cases(profile: str) -> None:
    prof = _profiles()[profile]
    for when, expected in _cases():
        assert c.posting_label(prof, when) == expected[profile], (profile, when)


def test_golden_cases_in_dubai_time_from_utc() -> None:
    """The same 12 cases given as UTC instants (Dubai = UTC+4) give the same labels."""
    from datetime import timedelta

    prof = _profiles()["P2"]
    for when, expected in _cases():
        utc = (when - timedelta(hours=4)).replace(tzinfo=UTC)
        assert c.posting_label(prof, utc) == expected["P2"]


def test_fy2021_2022_weekend_change_matches_answer_key() -> None:
    """Seed federal layer: Fri/Sat to 31-Dec-2021, Sat/Sun from 1-Jan-2022."""
    prof = c.CalendarProfile(weeks=c.seed_weeks(), holidays=c.seed_holidays())
    with (DATA / "fy2021_2022.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    off = {r["line_id"] for r in rows
           if c.posting_label(prof, date.fromisoformat(r["posting_date"])) == c.NON_WORKING}
    planted = {a["line_id"] for a in answer_key() if a["file"] == "fy2021_2022.csv"}
    assert len(planted) == 60 and off == planted
