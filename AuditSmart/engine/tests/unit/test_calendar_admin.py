"""calendar_admin (prompt 3.10): layer edits, validation, Excel, Asia/Dubai, STALE."""

from __future__ import annotations

import io
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import pytest
from openpyxl import Workbook, load_workbook
from sqlalchemy import select

from app.core.db import session_factory
from app.models import AuditLog, Dataset, EmirateProfile, Engagement, Holiday, JeRun
from app.services import calendar as c
from app.services import calendar_admin as adm

E = adm.CalendarAdminError


def _cid(engagement: str) -> str:
    with session_factory()() as s:
        eng = s.get(Engagement, engagement)
        assert eng is not None
        return eng.client_id


def _run(engagement: str, start: date, end: date) -> str:
    """A current JE run as je_tests stores it (calendar hash + period)."""
    rc = c.resolve_engagement(engagement, start, end)
    with session_factory()() as s:
        ds = Dataset(engagement_id=engagement, file_name="gl.csv", status="ready")
        s.add(ds)
        s.flush()
        run = JeRun(engagement_id=engagement, dataset_id=ds.id, parameters={},
                    calendar_hash=rc.hash, engine_version="t",
                    result={"calendar": {"start": start.isoformat(), "end": end.isoformat()}})
        s.add(run)
        s.commit()
        return run.id


def _status(run_id: str) -> str:
    with session_factory()() as s:
        r = s.get(JeRun, run_id)
        assert r is not None
        return r.status


# ---------------------------------------------------------------- parsing helpers
def test_parse_and_format_days() -> None:
    assert adm.parse_days("Sat, sun") == [6, 7]
    assert adm.parse_days("") == []
    assert adm.parse_half_days("Fri 12:00; thu 9:30") == {"5": "12:00", "4": "09:30"}
    assert adm.fmt_days([7, 5]) == "Fri, Sun"
    assert adm.fmt_half({"5": "12:00"}) == "Fri 12:00"
    assert adm.fmt_half(None) == ""
    for bad in ("Funday", "Sat, Sat"):
        with pytest.raises(E):
            adm.parse_days(bad)
    with pytest.raises(E, match="Fri 12:00"):
        adm.parse_half_days("Fri noon")
    assert adm.half_day_time("12:00") == time(12, 0)
    with pytest.raises(E, match="not a date"):
        adm._date("31/12/2025", "Date")
    assert adm._date(datetime(2025, 1, 2, 3), "x") == date(2025, 1, 2)
    assert adm._emirate("dubai") == "Dubai" and adm._emirate("FEDERAL") == "FEDERAL"
    with pytest.raises(E, match="Unknown emirate"):
        adm._emirate("Atlantis")


def test_to_dubai_and_posting_label() -> None:
    naive = datetime(2025, 1, 10, 12, 30)
    assert c.to_dubai(naive).utcoffset() == timedelta(hours=4)
    assert c.to_dubai(naive).hour == 12  # naive = already Dubai wall time
    utc = datetime(2025, 1, 10, 8, 30, tzinfo=UTC)
    assert c.to_dubai(utc).hour == 12
    p = c.CalendarProfile(weeks=c.seed_weeks(), holidays=c.seed_holidays())
    assert c.posting_label(p, utc) == c.AFTER_CUTOFF  # Fri 12:30 Dubai
    assert c.posting_label(p, datetime(2025, 1, 10, 7, 59, tzinfo=UTC)) == c.WORKING
    assert c.posting_label(p, date(2025, 1, 10), time(12, 0)) == c.WORKING  # at cut-off
    assert c.posting_label(p, date(2025, 1, 10)) == c.WORKING  # no time -> day only
    assert c.posting_label(p, date(2025, 1, 11)) == c.NON_WORKING


# ---------------------------------------------------------------- company layer
def test_company_layer_overlap_exceptions_and_stale(env: object, engagement: str) -> None:
    cid = _cid(engagement)
    run25 = _run(engagement, date(2025, 1, 1), date(2025, 12, 31))
    run21 = _run(engagement, date(2021, 1, 1), date(2021, 12, 31))
    with session_factory()() as s:
        # working-holiday exception on National Day: only the 2025 run goes STALE
        _, stale = adm.add_exception(s, cid, day=date(2025, 12, 2), type_="WORKING_DAY",
                                     note="stock count", user_id="m")
        assert [x["id"] for x in stale] == [run25]
        with pytest.raises(E, match="already exists"):
            adm.add_exception(s, cid, day=date(2025, 12, 2), type_="EXTRA_HOLIDAY",
                              note=None, user_id="m")
        with pytest.raises(E, match="Type must be"):
            adm.add_exception(s, cid, day=date(2025, 12, 5), type_="X", note=None,
                              user_id="m")
        s.commit()
    assert _status(run25) == "STALE" and _status(run21) == "current"
    st = c.resolve_engagement(engagement, date(2025, 12, 2), date(2025, 12, 2))
    assert st.status(date(2025, 12, 2)).reason == "working_exception"
    with session_factory()() as s:
        _, stale = adm.add_company_week(s, cid, off_days=[5], half_days={},
                                          effective_from=date(2021, 6, 1),
                                          effective_to=date(2021, 12, 31), user_id="m")
        assert [x["id"] for x in stale] == [run21]
        with pytest.raises(E, match="Overlapping company"):
            adm.add_company_week(s, cid, off_days=[7], half_days={},
                                 effective_from=date(2021, 12, 1), effective_to=None,
                                 user_id="m")
        s.rollback()
    with session_factory()() as s:
        with pytest.raises(E, match="both an off day"):
            adm.add_company_week(s, cid, off_days=[5], half_days={"5": "12:00"},
                                 effective_from=date(2026, 1, 1), effective_to=None,
                                 user_id="m")
        lay = adm.layers(s, cid)
        assert lay["federal_source"].startswith("seed") and len(lay["federal"]) == 2
        assert lay["exceptions"][0]["type"] == "WORKING_DAY"
        assert lay["company_weeks"] == []  # the overlapping add was rolled back
        ex_id = lay["exceptions"][0]["id"]
        assert adm.delete_company_item(s, cid, "exception", ex_id, "m") == []  # run25 stale
        with pytest.raises(E, match="not found"):
            adm.delete_company_item(s, cid, "workweek", 999, "m")
        s.commit()
        audits = {a.action for a in s.scalars(select(AuditLog)).all()}
    assert {"calendar_add", "calendar_delete", "stale"} <= audits
    with session_factory()() as s, pytest.raises(E, match="Client not found"):
        adm.layers(s, "nope")


def test_global_layers_materialise_seed_first(env: object, engagement: str) -> None:
    run = _run(engagement, date(2025, 1, 1), date(2025, 12, 31))
    before = c.resolve_engagement(engagement, date(2025, 1, 1), date(2025, 12, 31)).hash
    with session_factory()() as s:
        # provisional emirate holiday for Dubai (the client's emirate)
        row, stale = adm.add_holiday(s, day=date(2025, 7, 15), name="Provisional day",
                                     scope="EMIRATE", emirate="dubai", status="provisional",
                                     user_id="a")
        assert [x["id"] for x in stale] == [run]
        fed = s.scalars(select(Holiday).where(Holiday.scope == "FEDERAL")).all()
        assert len(fed) == len(c.seed_holidays())  # seed copied, nothing dropped
        with pytest.raises(E, match="already exists"):
            adm.add_holiday(s, day=date(2025, 7, 15), name="x", scope="EMIRATE",
                            emirate="Dubai", status="confirmed", user_id="a")
        for kw, msg in (({"scope": "CITY"}, "Scope"), ({"emirate": None}, "needs an emirate"),
                        ({"status": "maybe"}, "Status")):
            args: dict[str, Any] = {"day": date(2025, 8, 1), "name": "x", "scope": "EMIRATE",
                                    "emirate": "Dubai", "status": "confirmed", **kw}
            with pytest.raises(E, match=msg):
                adm.add_holiday(s, user_id="a", **args)
        h, _ = adm.update_holiday_status(s, row.id, "confirmed", "a")
        assert h.status == "confirmed"
        with pytest.raises(E, match="not found"):
            adm.update_holiday_status(s, 999, "confirmed", "a")
        with pytest.raises(E, match="Status"):
            adm.update_holiday_status(s, row.id, "x", "a")
        s.commit()
    rc = c.resolve_engagement(engagement, date(2025, 7, 15), date(2025, 7, 15))
    assert rc.status(date(2025, 7, 15)).reason == "holiday"
    with session_factory()() as s:
        # the seed's open-ended 2022 week is copied first, so a 2030 week overlaps it
        with pytest.raises(E, match="Overlapping federal"):
            adm.add_emirate_week(s, emirate="FEDERAL", off_days=[6, 7], half_days={},
                                 effective_from=date(2030, 1, 1), effective_to=None,
                                 user_id="a")
        s.rollback()
    with session_factory()() as s:
        n = s.scalars(select(EmirateProfile)).all()
        assert n == []
        adm.add_emirate_week(s, emirate="Sharjah", off_days=[5, 6, 7], half_days={},
                             effective_from=date(2025, 1, 1), effective_to=None, user_id="a")
        assert len(s.scalars(select(EmirateProfile)).all()) == 3  # 2 seed + Sharjah
        lay = adm.layers(s, _cid(engagement))
        assert lay["federal_source"] == "database" and lay["emirate_weeks"] == []
        assert lay["holiday_source"] == "database"
        adm.delete_global_item(s, "holiday", row.id, "a")
        with pytest.raises(E, match="not found"):
            adm.delete_global_item(s, "emirate_profile", 999, "a")
        s.commit()
    assert c.resolve_engagement(engagement, date(2025, 1, 1), date(2025, 12, 31)).hash == before
    sharjah = c.resolve_client(_cid(engagement), "Sharjah", date(2025, 1, 10), date(2025, 1, 10))
    assert sharjah.status(date(2025, 1, 10)).reason == "weekend"


# ---------------------------------------------------------------- Excel
def _book(sheets: dict[str, list[list[Any]]]) -> bytes:
    wb = Workbook()
    wb.remove(wb.active)  # type: ignore[arg-type]
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        for r in rows:
            ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


H = {k: list(v) for k, v in adm.SHEETS.items()}


def test_template_round_trip(env: object, engagement: str) -> None:
    with session_factory()() as s:
        body = adm.export_workbook(s, None)
    wb = load_workbook(io.BytesIO(body))
    assert wb.sheetnames == ["Instructions", "WorkWeeks", "Exceptions", "Holidays"]
    res = adm.parse_workbook(body, allow_holidays=False)
    assert res.errors == [] and res.preview()["counts"] == {"work_weeks": 1, "exceptions": 1,
                                                           "holidays": 0}
    cid = _cid(engagement)
    run = _run(engagement, date(2025, 1, 1), date(2025, 12, 31))
    with session_factory()() as s:
        out = adm.apply_import(s, cid, res, "m")
        s.commit()
    assert out["work_weeks"] == 1 and [x["id"] for x in out["stale"]] == [run]
    with session_factory()() as s:
        exp = load_workbook(io.BytesIO(adm.export_workbook(s, cid)))
    assert [c.value for c in exp["WorkWeeks"][2]][:3] == ["Sat, Sun", "Fri 12:00",
                                                          "2022-01-01"]
    assert exp["Exceptions"]["B2"].value == "WORKING_DAY"
    assert exp["Holidays"].max_row == 1  # DB holidays only; the seed is not exported
    with session_factory()() as s:  # re-import replaces, does not duplicate
        out = adm.apply_import(s, cid, adm.parse_workbook(adm.export_workbook(s, cid),
                                                          allow_holidays=True), "a")
        s.commit()
        assert len(adm.layers(s, cid)["company_weeks"]) == 1
        assert out["holidays_added"] == 0


def test_import_errors_are_located(env: object, engagement: str) -> None:
    body = _book({
        "WorkWeeks": [H["WorkWeeks"], ["Sat, Funday", "", "2025-01-01", None, None],
                      ["Sun", "Fri 25:00", "2025-01-01", None, None],
                      ["Sun", "", "bad", None, None], ["Sun", "", "2025-01-01", "x", None],
                      ["Fri", "Fri 12:00", "2025-01-01", None, None], [None] * 5],
        "Exceptions": [H["Exceptions"], ["2025-12-02", "WORKING_DAY", None],
                       ["2025-12-02", "EXTRA_HOLIDAY", None], ["2025-12-03", "NOPE", None]],
        "Holidays": [H["Holidays"], ["2025-07-15", "Day", "FEDERAL", None, "confirmed"]],
    })
    res = adm.parse_workbook(body, allow_holidays=False)
    got = {(e["sheet"], e["row"], e["column"]) for e in res.errors}
    assert got == {("WorkWeeks", 2, "Off days"), ("WorkWeeks", 3, "Half days"),
                   ("WorkWeeks", 4, "Effective from"), ("WorkWeeks", 5, "Effective to"),
                   ("WorkWeeks", 6, ""), ("Exceptions", 3, "Date"),
                   ("Exceptions", 4, "Type"), ("Holidays", 2, "")}
    assert not res.preview()["ok"]
    with session_factory()() as s, pytest.raises(E, match="preview"):
        adm.apply_import(s, _cid(engagement), res, "m")
    hol = _book({"WorkWeeks": [H["WorkWeeks"], ["Sat, Sun", "", "2022-01-01", None, None],
                               ["Sun", "", "2024-01-01", None, None]],
                 "Exceptions": [H["Exceptions"]],
                 "Holidays": [H["Holidays"],
                              ["2025-07-15", "Day", "EMIRATE", "Dubai", "provisional"],
                              ["2025-07-16", "", "FEDERAL", None, None],
                              ["2025-07-17", "D", "STATE", None, None],
                              ["2025-07-18", "D", "FEDERAL", "Dubai", None],
                              ["2025-07-19", "D", "FEDERAL", None, "maybe"],
                              ["2025-07-20", "D", "EMIRATE", "Atlantis", None]]})
    res = adm.parse_workbook(hol, allow_holidays=True)
    assert [(e["sheet"], e["row"], e["column"]) for e in res.errors] == [
        ("Holidays", 3, "Name"), ("Holidays", 4, "Scope"), ("Holidays", 5, "Emirate"),
        ("Holidays", 6, "Status"), ("Holidays", 7, "Emirate"),
        ("WorkWeeks", 0, "Effective from")]
    assert res.holidays[0]["status"] == "provisional"


def test_import_structure_errors(env: object, engagement: str) -> None:
    with pytest.raises(E, match="readable"):
        adm.parse_workbook(b"not a zip", allow_holidays=False)
    res = adm.parse_workbook(_book({"WorkWeeks": [["Wrong"]], "Exceptions": []}),
                             allow_holidays=False)
    assert [e["message"][:9] for e in res.errors] == ["Header mu", "Header mu",
                                                       "Sheet 'Ho"]
    big = _book({"WorkWeeks": [H["WorkWeeks"], *[[None] * 5] * (adm.MAX_ROWS + 1)],
                 "Exceptions": [H["Exceptions"]], "Holidays": [H["Holidays"]]})
    assert "More than" in adm.parse_workbook(big, allow_holidays=False).errors[0]["message"]
    ok = _book({"WorkWeeks": [H["WorkWeeks"]], "Exceptions": [H["Exceptions"]],
                "Holidays": [H["Holidays"], ["2025-07-15", "Day", "FEDERAL", None, None],
                             ["2025-01-01", "New Year", "FEDERAL", None, None]]})
    res = adm.parse_workbook(ok, allow_holidays=True)
    with session_factory()() as s:
        out = adm.apply_import(s, _cid(engagement), res, "a")
        s.commit()
    assert out["holidays_added"] == 1 and out["holidays_skipped"] == 1


def test_mark_stale_skips_incomplete_and_unresolvable(env: object, engagement: str) -> None:
    run = _run(engagement, date(2025, 1, 1), date(2025, 1, 31))
    with session_factory()() as s:
        r = s.get(JeRun, run)
        assert r is not None
        r.result = {}
        ds = s.scalars(select(Dataset)).first()
        assert ds is not None
        s.add(JeRun(engagement_id=engagement, dataset_id=ds.id, parameters={},
                    calendar_hash=None, engine_version="t"))
        s.commit()
        assert adm.mark_stale(s, client_ids=None, user_id=None, reason="t") == []
        assert adm.mark_stale(s, client_ids=["other"], user_id=None, reason="t") == []
        r.result = {"calendar": {"start": "2025-01-01", "end": "2025-01-31"}}
        s.commit()
    from unittest.mock import patch

    with session_factory()() as s, patch.object(c, "load_profile",
                                                side_effect=c.CalendarError("x")):
        assert len(adm.mark_stale(s, client_ids=None, user_id=None, reason="t")) == 1
