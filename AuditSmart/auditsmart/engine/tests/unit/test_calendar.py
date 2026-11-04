"""Working-calendar core (resolve + precedence) used by JE tests (prompt 3.4; 3.10 extends)."""

from __future__ import annotations

from datetime import date, time

import pytest

from app.services import calendar as c

SAT_SUN = c.WorkWeek(frozenset({6, 7}), date(2022, 1, 1), half_days={5: time(12, 0)})
FRI_SAT = c.WorkWeek(frozenset({5, 6}), date(2018, 1, 1), date(2021, 12, 31))


def _prof(**kw: object) -> c.CalendarProfile:
    base: dict[str, object] = {"emirate": "Dubai", "weeks": (FRI_SAT, SAT_SUN)}
    base.update(kw)
    return c.CalendarProfile(**base)  # type: ignore[arg-type]


def test_weekend_change_on_1_jan_2022() -> None:
    p = _prof()
    assert c.day_status(p, date(2021, 12, 31)).reason == "weekend"  # Friday, Fri/Sat regime
    assert c.day_status(p, date(2021, 12, 26)).is_working  # Sunday, working before change
    st = c.day_status(p, date(2022, 1, 7))  # Friday after the change
    assert st.is_working and st.reason == "half_day" and st.half_day_cutoff == time(12, 0)
    assert c.day_status(p, date(2022, 1, 9)).reason == "weekend"  # Sunday
    assert c.day_status(p, date(2022, 1, 10)).reason == "working"


@pytest.mark.parametrize(("off", "expected_off"), [({7}, 1), ({6, 7}, 2), ({5, 6, 7}, 3)])
def test_one_two_three_off_days(off: set[int], expected_off: int) -> None:
    company = c.WorkWeek(frozenset(off), date(2025, 1, 1), level="company")
    p = _prof(weeks=(SAT_SUN, company))
    days = c.resolve(p, date(2025, 1, 6), date(2025, 1, 12))  # Mon..Sun
    assert sum(not d.is_working for d in days) == expected_off
    assert all(d.source == "company" for d in days)


def test_precedence_exception_over_company_over_emirate_over_federal() -> None:
    emirate = c.WorkWeek(frozenset({5, 6, 7}), date(2022, 1, 1), level="emirate")
    p = _prof(weeks=(SAT_SUN, emirate))
    assert c.day_status(p, date(2025, 1, 10)).source == "emirate"  # Friday off in emirate
    company = c.WorkWeek(frozenset({7}), date(2025, 1, 1), level="company")
    hol = c.HolidayDay(date(2025, 1, 14), "Test holiday")
    p2 = _prof(
        weeks=(SAT_SUN, emirate, company),
        holidays=(hol,),
        exceptions=(
            c.CompanyException(date(2025, 1, 14), "WORKING_DAY", "stock count"),
            c.CompanyException(date(2025, 1, 15), "EXTRA_HOLIDAY", "closure"),
        ),
    )
    assert c.day_status(p2, date(2025, 1, 10)).is_working  # company: only Sunday off
    assert c.day_status(p2, date(2025, 1, 14)).reason == "working_exception"
    st = c.day_status(p2, date(2025, 1, 15))
    assert not st.is_working and st.reason == "company_closure" and st.holiday_name == "closure"


def test_holidays_federal_emirate_and_provisional() -> None:
    hols = (
        c.HolidayDay(date(2025, 1, 14), "Fed", status="provisional"),
        c.HolidayDay(date(2025, 1, 15), "Dubai only", "EMIRATE", "Dubai"),
        c.HolidayDay(date(2025, 1, 16), "Sharjah only", "EMIRATE", "Sharjah"),
        c.HolidayDay(date(2025, 1, 18), "On a Saturday"),
    )
    p = _prof(holidays=hols)
    st = c.day_status(p, date(2025, 1, 14))
    assert st.reason == "holiday" and st.provisional and st.source == "federal"
    assert c.day_status(p, date(2025, 1, 15)).source == "emirate"
    assert c.day_status(p, date(2025, 1, 16)).is_working
    assert c.day_status(p, date(2025, 1, 18)).reason == "holiday"  # holiday before weekend
    rc = c.ResolvedCalendar(p, date(2025, 1, 13), date(2025, 1, 19))
    s = rc.summary()
    assert s["provisional_holidays"] == ["2025-01-14"] and s["non_working_days"] == 4
    assert s["half_days"] == 1 and len(s["hash"]) == 64
    assert rc.status(date(2025, 2, 3)).is_working  # lazy outside the range


def test_hash_changes_with_layers() -> None:
    a = c.ResolvedCalendar(_prof(), date(2025, 1, 1), date(2025, 1, 31)).hash
    b = c.ResolvedCalendar(
        _prof(holidays=(c.HolidayDay(date(2025, 1, 2), "X"),)), date(2025, 1, 1), date(2025, 1, 31)
    ).hash
    assert a != b and a == c.ResolvedCalendar(_prof(), date(2025, 1, 1), date(2025, 1, 31)).hash


def test_errors() -> None:
    with pytest.raises(c.CalendarError, match="No work week"):
        c.day_status(c.CalendarProfile(), date(2025, 1, 1))
    with pytest.raises(c.CalendarError, match="Overlapping"):
        c.CalendarProfile(weeks=(SAT_SUN, c.WorkWeek(frozenset({6}), date(2024, 1, 1))))
    with pytest.raises(c.CalendarError, match="Overlapping"):
        c.CalendarProfile(weeks=(c.WorkWeek(frozenset({6}), date(2020, 1, 1)), SAT_SUN))
    with pytest.raises(c.CalendarError, match="Two company"):
        c.CalendarProfile(
            weeks=(SAT_SUN,),
            exceptions=(
                c.CompanyException(date(2025, 1, 1), "WORKING_DAY"),
                c.CompanyException(date(2025, 1, 1), "EXTRA_HOLIDAY"),
            ),
        )
    with pytest.raises(c.CalendarError, match="Exception type"):
        c.CompanyException(date(2025, 1, 1), "HOLIDAY")
    with pytest.raises(c.CalendarError, match="level"):
        c.WorkWeek(frozenset(), date(2025, 1, 1), level="city")
    with pytest.raises(c.CalendarError, match="Weekdays"):
        c.WorkWeek(frozenset({8}), date(2025, 1, 1))
    with pytest.raises(c.CalendarError, match="ends before"):
        c.WorkWeek(frozenset({6}), date(2025, 1, 2), date(2025, 1, 1))
    with pytest.raises(c.CalendarError, match="both"):
        c.WorkWeek(frozenset({5}), date(2025, 1, 1), half_days={5: time(12)})
    with pytest.raises(c.CalendarError, match="end date"):
        c.resolve(_prof(), date(2025, 1, 2), date(2025, 1, 1))


def test_seed_layers_match_documented_facts() -> None:
    weeks, hols = c.seed_weeks(), c.seed_holidays()
    assert {h.day for h in hols} >= {date(2025, 12, 1), date(2025, 12, 2), date(2022, 1, 1)}
    assert len([h for h in hols if h.day.year == 2025]) == 12
    p = c.CalendarProfile(weeks=weeks, holidays=hols)
    assert c.day_status(p, date(2021, 12, 10)).reason == "weekend"
    assert c.day_status(p, date(2025, 3, 7)).half_day_cutoff == time(12, 0)
    w = c.WorkWeek.from_dict(
        {
            "off_days": [6, 7],
            "half_days": {"5": "11:30"},
            "effective_from": "2025-01-01",
            "effective_to": None,
        }
    )
    assert w.half_days[5] == time(11, 30) and w.effective_to is None


def test_db_loader_layers(env: object, engagement: str) -> None:
    from app.core.db import session_factory
    from app.models import (
        Client,
        CompanyException,
        CompanyWorkweek,
        EmirateProfile,
        Engagement,
        Holiday,
    )

    with session_factory()() as s:
        eng = s.get(Engagement, engagement)
        assert eng is not None
        cl = s.get(Client, eng.client_id)
        assert cl is not None
        cid = cl.id
    seeded = c.resolve_engagement(engagement, date(2025, 1, 1), date(2025, 12, 31))
    assert seeded.status(date(2025, 12, 2)).reason == "holiday"  # seed fallback
    with session_factory()() as s:
        s.add_all(
            [
                EmirateProfile(
                    emirate="FEDERAL",
                    off_days=[6, 7],
                    half_days={},
                    effective_from=date(2022, 1, 1),
                ),
                EmirateProfile(
                    emirate="Dubai",
                    off_days=[5, 6, 7],
                    half_days=None,
                    effective_from=date(2025, 6, 1),
                ),
                CompanyWorkweek(
                    client_id=cid,
                    off_days=[7],
                    half_days={"6": "13:00"},
                    effective_from=date(2025, 10, 1),
                ),
                CompanyException(client_id=cid, date=date(2025, 12, 2), type="WORKING_DAY"),
                Holiday(
                    date=date(2025, 1, 2), name="DB holiday", scope="FEDERAL", status="provisional"
                ),
            ]
        )
        s.commit()
    rc = c.resolve_engagement(engagement, date(2025, 1, 1), date(2025, 12, 31))
    assert rc.hash != seeded.hash
    assert rc.status(date(2025, 1, 2)).provisional  # DB federal holidays replace the seed
    assert rc.status(date(2025, 12, 1)).is_working  # seed holiday no longer applies
    assert rc.status(date(2025, 3, 7)).reason == "working"  # federal DB: no half day
    assert rc.status(date(2025, 6, 6)).source == "emirate"
    assert rc.status(date(2025, 10, 4)).half_day_cutoff == time(13, 0)
    assert rc.status(date(2025, 12, 2)).reason == "working_exception"
    with pytest.raises(c.CalendarError, match="Engagement"):
        c.resolve_engagement("nope", date(2025, 1, 1), date(2025, 1, 2))
    with pytest.raises(c.CalendarError, match="Client"):
        c.load_profile("nope")
