"""Working-calendar administration (prompt 3.10, SPEC 3.5 / Appendix A).

Layer edits (company work weeks and exceptions per client; emirate / federal work weeks
and holidays for Admins), validation (non-overlapping periods, one exception per date),
Excel template import (preview with row-level errors, then apply) and export, and STALE
marking: after any change every current JE run whose stored ``calendar_hash`` no longer
matches the calendar re-resolved for the same period becomes STALE (audit_log "stale").
"""

from __future__ import annotations

import io
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    Client,
    CompanyException,
    CompanyWorkweek,
    EmirateProfile,
    Engagement,
    Holiday,
    JeRun,
)
from app.services import calendar as cal

IMPLEMENTED_BY_PROMPT = "3.10"

DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
EMIRATES = ("Abu Dhabi", "Dubai", "Sharjah", "Ajman", "Umm Al Quwain", "Ras Al Khaimah",
            "Fujairah")
HOLIDAY_STATUSES = ("confirmed", "provisional")
SHEETS = {
    "WorkWeeks": ("Off days", "Half days", "Effective from", "Effective to", "Source"),
    "Exceptions": ("Date", "Type", "Note"),
    "Holidays": ("Date", "Name", "Scope", "Emirate", "Status"),
}
MAX_ROWS = 5000
_HALF = re.compile(r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([01]?\d|2[0-3]):([0-5]\d)$")


class CalendarAdminError(ValueError):
    def __init__(self, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# ------------------------------------------------------------- helpers
def parse_days(text: str) -> list[int]:
    out: list[int] = []
    for part in [p.strip() for p in str(text or "").replace(";", ",").split(",") if p.strip()]:
        name = part[:3].title()
        if name not in DAYS:
            raise CalendarAdminError(f"'{part}' is not a weekday (use Mon..Sun).")
        out.append(DAYS.index(name) + 1)
    if len(set(out)) != len(out):
        raise CalendarAdminError("A weekday is listed twice.")
    return sorted(out)


def parse_half_days(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in [p.strip() for p in str(text or "").replace(";", ",").split(",") if p.strip()]:
        m = _HALF.match(part[:3].title() + part[3:])
        if not m:
            raise CalendarAdminError(f"Half day '{part}' must look like 'Fri 12:00'.")
        out[str(DAYS.index(m.group(1)) + 1)] = f"{int(m.group(2)):02d}:{m.group(3)}"
    return out


def fmt_days(days: Iterable[int]) -> str:
    return ", ".join(DAYS[d - 1] for d in sorted(days))


def fmt_half(half: dict[str, str] | None) -> str:
    return ", ".join(f"{DAYS[int(k) - 1]} {v}" for k, v in sorted((half or {}).items()))


def _date(v: Any, what: str) -> date:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v).strip())
    except ValueError:
        raise CalendarAdminError(f"{what} '{v}' is not a date (YYYY-MM-DD).") from None


def _week(off: list[int], half: dict[str, str], start: date, end: date | None,
          level: str) -> cal.WorkWeek:
    try:
        return cal.WorkWeek(frozenset(off), start, end,
                            {int(k): cal._parse_time(v) for k, v in half.items()}, level=level)
    except cal.CalendarError as exc:
        raise CalendarAdminError(str(exc)) from None


def _audit(s: Session, user: str | None, action: str, entity: str, entity_id: str | None,
           new: dict[str, Any] | None, old: dict[str, Any] | None = None) -> None:
    s.add(AuditLog(user_id=user, action=action, entity=entity, entity_id=entity_id,
                   old=old, new=new))


def get_client(s: Session, client_id: str) -> Client:
    c = s.get(Client, client_id)
    if c is None:
        raise CalendarAdminError("Client not found.", 404)
    return c


def _emirate(name: str) -> str:
    if name == "FEDERAL":
        return name
    for e in EMIRATES:
        if e.lower() == name.strip().lower():
            return e
    raise CalendarAdminError(f"Unknown emirate '{name}' (use FEDERAL or one of "
                             f"{', '.join(EMIRATES)}).")


# --------------------------------------------------------------- views
def week_row(r: CompanyWorkweek | EmirateProfile, level: str) -> dict[str, Any]:
    return {"id": r.id, "level": level, "off_days": sorted(r.off_days),
            "half_days": r.half_days or {}, "effective_from": r.effective_from.isoformat(),
            "effective_to": r.effective_to.isoformat() if r.effective_to else None,
            "emirate": getattr(r, "emirate", None)}


def layers(s: Session, client_id: str) -> dict[str, Any]:
    c = get_client(s, client_id)
    fed = s.scalars(select(EmirateProfile).where(EmirateProfile.emirate == "FEDERAL")
                    .order_by(EmirateProfile.effective_from)).all()
    em = s.scalars(select(EmirateProfile).where(EmirateProfile.emirate == c.emirate)
                   .order_by(EmirateProfile.effective_from)).all()
    cw = s.scalars(select(CompanyWorkweek).where(CompanyWorkweek.client_id == client_id)
                   .order_by(CompanyWorkweek.effective_from)).all()
    ex = s.scalars(select(CompanyException).where(CompanyException.client_id == client_id)
                   .order_by(CompanyException.date)).all()
    hol = s.scalars(select(Holiday).order_by(Holiday.date)).all()
    seed_fed = not fed
    return {
        "client_id": client_id, "emirate": c.emirate,
        "federal": [week_row(r, "federal") for r in fed] if fed else [
            {"id": None, "level": "federal", "off_days": sorted(w.off_days),
             "half_days": {str(k): v.strftime("%H:%M") for k, v in w.half_days.items()},
             "effective_from": w.effective_from.isoformat(),
             "effective_to": w.effective_to.isoformat() if w.effective_to else None,
             "emirate": "FEDERAL", "source": w.source} for w in cal.seed_weeks()],
        "federal_source": "seed (pending_verification)" if seed_fed else "database",
        "emirate_weeks": [week_row(r, "emirate") for r in em],
        "company_weeks": [week_row(r, "company") for r in cw],
        "exceptions": [{"id": r.id, "date": r.date.isoformat(), "type": r.type,
                        "note": r.note} for r in ex],
        "holidays": [{"id": h.id, "date": h.date.isoformat(), "name": h.name,
                      "scope": h.scope, "emirate": h.emirate, "status": h.status}
                     for h in hol],
        "holiday_source": "database" if any(h.scope == "FEDERAL" for h in hol)
        else "seed (pending_verification)",
    }


# ---------------------------------------------------------------- STALE
def mark_stale(s: Session, *, client_ids: Iterable[str] | None, user_id: str | None,
               reason: str) -> list[dict[str, Any]]:
    """JE runs whose calendar for the same period now hashes differently become STALE."""
    s.flush()
    q = select(JeRun).where(JeRun.status != "STALE")
    out: list[dict[str, Any]] = []
    wanted = set(client_ids) if client_ids is not None else None
    for run in s.scalars(q).all():
        eng = s.get(Engagement, run.engagement_id)
        if eng is None or (wanted is not None and eng.client_id not in wanted):
            continue
        info = (run.result or {}).get("calendar") or {}
        if not run.calendar_hash or not info.get("start") or not info.get("end"):
            continue
        try:
            now = cal.ResolvedCalendar(cal.load_profile(eng.client_id, s),
                                       date.fromisoformat(info["start"]),
                                       date.fromisoformat(info["end"])).hash
        except cal.CalendarError:
            now = "unresolvable"
        if now == run.calendar_hash:
            continue
        run.status = "STALE"
        item = {"kind": "je_run", "id": run.id, "engagement_id": run.engagement_id}
        out.append(item)
        _audit(s, user_id, "stale", "je_run", run.id,
               {"status": "STALE", "reason": reason, "calendar_hash": now},
               {"status": "current", "calendar_hash": run.calendar_hash})
    return out


def _validate_client(s: Session, client_id: str) -> None:
    try:
        cal.load_profile(client_id, s)
    except cal.CalendarError as exc:
        raise CalendarAdminError(str(exc), 409) from None


def _validate_all(s: Session) -> None:
    for cid in s.scalars(select(Client.id)).all():
        _validate_client(s, cid)


# ----------------------------------------------------------- company layer
def add_company_week(s: Session, client_id: str, *, off_days: list[int],
                     half_days: dict[str, str], effective_from: date,
                     effective_to: date | None, user_id: str) -> tuple[CompanyWorkweek,
                                                                       list[dict[str, Any]]]:
    get_client(s, client_id)
    _week(off_days, half_days, effective_from, effective_to, "company")
    row = CompanyWorkweek(client_id=client_id, off_days=off_days, half_days=half_days,
                          effective_from=effective_from, effective_to=effective_to)
    s.add(row)
    s.flush()
    _validate_client(s, client_id)
    _audit(s, user_id, "calendar_add", "company_workweek", str(row.id),
           week_row(row, "company"))
    return row, mark_stale(s, client_ids=[client_id], user_id=user_id,
                           reason="company work week added")


def add_exception(s: Session, client_id: str, *, day: date, type_: str, note: str | None,
                  user_id: str) -> tuple[CompanyException, list[dict[str, Any]]]:
    get_client(s, client_id)
    if type_ not in cal.EXCEPTION_TYPES:
        raise CalendarAdminError(f"Type must be one of {', '.join(cal.EXCEPTION_TYPES)}.")
    if s.scalar(select(CompanyException).where(CompanyException.client_id == client_id,
                                               CompanyException.date == day)):
        raise CalendarAdminError(f"An exception already exists on {day.isoformat()}.", 409)
    row = CompanyException(client_id=client_id, date=day, type=type_, note=note)
    s.add(row)
    s.flush()
    _audit(s, user_id, "calendar_add", "company_exception", str(row.id),
           {"date": day.isoformat(), "type": type_, "note": note})
    return row, mark_stale(s, client_ids=[client_id], user_id=user_id,
                           reason="company exception added")


def delete_company_item(s: Session, client_id: str, kind: str, item_id: int,
                        user_id: str) -> list[dict[str, Any]]:
    row: CompanyWorkweek | CompanyException | None = (
        s.get(CompanyWorkweek, item_id) if kind == "workweek"
        else s.get(CompanyException, item_id))
    if row is None or row.client_id != client_id:
        raise CalendarAdminError("Calendar item not found.", 404)
    s.delete(row)
    _audit(s, user_id, "calendar_delete", f"company_{kind}", str(item_id), None,
           {"client_id": client_id})
    return mark_stale(s, client_ids=[client_id], user_id=user_id,
                      reason=f"company {kind} deleted")


# ------------------------------------------------------------ global layers
def materialise_seed(s: Session, what: str, user_id: str | None) -> int:
    """Copy the seed federal work weeks / holidays into the tables before the first DB edit.

    load_profile() uses the seed only while the tables hold no FEDERAL rows, so the first
    Admin edit would otherwise silently drop every seeded item (D32)."""
    n = 0
    if what == "weeks" and not s.scalar(select(EmirateProfile.id).where(
            EmirateProfile.emirate == "FEDERAL").limit(1)):
        for w in cal.seed_weeks():
            s.add(EmirateProfile(emirate="FEDERAL", off_days=sorted(w.off_days),
                                 half_days={str(k): v.strftime("%H:%M")
                                            for k, v in w.half_days.items()},
                                 effective_from=w.effective_from,
                                 effective_to=w.effective_to))
            n += 1
    if what == "holidays" and not s.scalar(select(Holiday.id).where(
            Holiday.scope == "FEDERAL").limit(1)):
        for h in cal.seed_holidays():
            s.add(Holiday(date=h.day, name=h.name, scope=h.scope, emirate=h.emirate,
                          status=h.status))
            n += 1
    if n:
        s.flush()
        _audit(s, user_id, "calendar_seed_materialised", what, None, {"rows": n})
    return n


def add_emirate_week(s: Session, *, emirate: str, off_days: list[int],
                     half_days: dict[str, str], effective_from: date,
                     effective_to: date | None, user_id: str
                     ) -> tuple[EmirateProfile, list[dict[str, Any]]]:
    em = _emirate(emirate)
    level = "federal" if em == "FEDERAL" else "emirate"
    _week(off_days, half_days, effective_from, effective_to, level)
    materialise_seed(s, "weeks", user_id)
    row = EmirateProfile(emirate=em, off_days=off_days, half_days=half_days,
                         effective_from=effective_from, effective_to=effective_to)
    s.add(row)
    s.flush()
    try:
        cal.check_no_overlap(
            _week(list(r.off_days), dict(r.half_days or {}), r.effective_from, r.effective_to,
                  level)
            for r in s.scalars(select(EmirateProfile).where(EmirateProfile.emirate == em)))
    except cal.CalendarError as exc:
        raise CalendarAdminError(str(exc), 409) from None
    _validate_all(s)
    _audit(s, user_id, "calendar_add", "emirate_profile", str(row.id), week_row(row, level))
    return row, mark_stale(s, client_ids=None, user_id=user_id,
                           reason=f"{em} work week added")


def add_holiday(s: Session, *, day: date, name: str, scope: str, emirate: str | None,
                status: str, user_id: str) -> tuple[Holiday, list[dict[str, Any]]]:
    scope = scope.upper()
    if scope not in ("FEDERAL", "EMIRATE"):
        raise CalendarAdminError("Scope must be FEDERAL or EMIRATE.")
    if (scope == "EMIRATE") != bool(emirate):
        raise CalendarAdminError("An EMIRATE holiday needs an emirate; a FEDERAL one none.")
    em = _emirate(emirate) if emirate else None
    if status not in HOLIDAY_STATUSES:
        raise CalendarAdminError("Status must be confirmed or provisional.")
    materialise_seed(s, "holidays", user_id)
    if s.scalar(select(Holiday).where(Holiday.date == day, Holiday.scope == scope,
                                      Holiday.emirate.is_(None) if em is None
                                      else Holiday.emirate == em)):
        raise CalendarAdminError(f"A {scope} holiday already exists on {day.isoformat()}.",
                                 409)
    row = Holiday(date=day, name=name.strip(), scope=scope, emirate=em, status=status)
    s.add(row)
    s.flush()
    _audit(s, user_id, "calendar_add", "holiday", str(row.id),
           {"date": day.isoformat(), "name": row.name, "scope": scope, "emirate": em,
            "status": status})
    return row, mark_stale(s, client_ids=None, user_id=user_id, reason="holiday added")


def update_holiday_status(s: Session, holiday_id: int, status: str,
                          user_id: str) -> tuple[Holiday, list[dict[str, Any]]]:
    row = s.get(Holiday, holiday_id)
    if row is None:
        raise CalendarAdminError("Holiday not found.", 404)
    if status not in HOLIDAY_STATUSES:
        raise CalendarAdminError("Status must be confirmed or provisional.")
    old = row.status
    row.status = status
    _audit(s, user_id, "calendar_update", "holiday", str(row.id), {"status": status},
           {"status": old})
    return row, mark_stale(s, client_ids=None, user_id=user_id,
                           reason="holiday status changed")


def delete_global_item(s: Session, kind: str, item_id: int,
                       user_id: str) -> list[dict[str, Any]]:
    row: EmirateProfile | Holiday | None = (
        s.get(EmirateProfile, item_id) if kind == "emirate_profile" else s.get(Holiday, item_id))
    if row is None:
        raise CalendarAdminError("Calendar item not found.", 404)
    s.delete(row)
    _audit(s, user_id, "calendar_delete", kind, str(item_id), None, None)
    return mark_stale(s, client_ids=None, user_id=user_id, reason=f"{kind} deleted")


# ------------------------------------------------------------------- Excel
_HEAD = Font(bold=True, color="FFFFFF")
_FILL = PatternFill("solid", fgColor="1F4E78")


def _sheet(wb: Workbook, name: str, rows: Iterable[Iterable[Any]]) -> None:
    ws = wb.create_sheet(name)
    ws.append(list(SHEETS[name]))
    for c in ws[1]:
        c.font, c.fill = _HEAD, _FILL
    for r in rows:
        ws.append(list(r))
    for i, h in enumerate(SHEETS[name]):
        ws.column_dimensions[chr(65 + i)].width = max(14, len(h) + 4)


def export_workbook(s: Session, client_id: str | None) -> bytes:
    """Template (client_id None, with one example row each) or the client's calendar."""
    wb = Workbook()
    info = wb.active
    assert info is not None
    info.title = "Instructions"
    for line in (
        "AuditSmart working-calendar template (prompt 3.10).",
        "WorkWeeks: company work weeks. Off days like 'Sat, Sun'; half days like 'Fri 12:00' "
        "(Asia/Dubai time); dates YYYY-MM-DD; leave 'Effective to' empty for open-ended. "
        "Periods must not overlap.",
        "Exceptions: Type EXTRA_HOLIDAY (company closed) or WORKING_DAY (works on a "
        "weekend or public holiday). One row per date.",
        "Holidays: Scope FEDERAL (no emirate) or EMIRATE (with emirate); Status confirmed or "
        "provisional. Only an Admin can import holidays; others leave this sheet empty.",
        "Import: upload with apply=false first to preview errors; apply=true replaces the "
        "client's work weeks and exceptions and adds new holidays.",
    ):
        info.append([line])
    info.column_dimensions["A"].width = 120
    if client_id is None:
        _sheet(wb, "WorkWeeks", [["Sat, Sun", "Fri 12:00", "2022-01-01", None, "example"]])
        _sheet(wb, "Exceptions", [["2025-12-02", "WORKING_DAY", "example: worked on the "
                                   "National Day holiday"]])
        _sheet(wb, "Holidays", [])
    else:
        lay = layers(s, client_id)
        _sheet(wb, "WorkWeeks", [[fmt_days(w["off_days"]), fmt_half(w["half_days"]),
                                  w["effective_from"], w["effective_to"], ""]
                                 for w in lay["company_weeks"]])
        _sheet(wb, "Exceptions", [[e["date"], e["type"], e["note"]]
                                  for e in lay["exceptions"]])
        _sheet(wb, "Holidays", [[h["date"], h["name"], h["scope"], h["emirate"], h["status"]]
                                for h in lay["holidays"]])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@dataclass
class ImportResult:
    weeks: list[dict[str, Any]] = field(default_factory=list)
    exceptions: list[dict[str, Any]] = field(default_factory=list)
    holidays: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)

    def preview(self) -> dict[str, Any]:
        return {"ok": not self.errors, "counts": {"work_weeks": len(self.weeks),
                                                  "exceptions": len(self.exceptions),
                                                  "holidays": len(self.holidays)},
                "errors": self.errors, "work_weeks": self.weeks,
                "exceptions": self.exceptions, "holidays": self.holidays}


def _cell(v: Any) -> Any:
    return v.strip() if isinstance(v, str) else v


def parse_workbook(body: bytes, *, allow_holidays: bool) -> ImportResult:
    res = ImportResult()
    try:
        wb = load_workbook(io.BytesIO(body), read_only=True, data_only=True)
    except Exception:  # zipfile / openpyxl errors
        raise CalendarAdminError("The file is not a readable .xlsx workbook.") from None

    def err(sheet: str, row: int, column: str, message: str) -> None:
        res.errors.append({"sheet": sheet, "row": row, "column": column, "message": message})

    for name, head in SHEETS.items():
        if name not in wb.sheetnames:
            err(name, 0, "", f"Sheet '{name}' is missing (use the template).")
            continue
        rows = list(wb[name].iter_rows(values_only=True))
        got = tuple(str(_cell(h) or "") for h in (rows[0] if rows else ()))[:len(head)]
        if got != head:
            err(name, 1, "", f"Header must be: {', '.join(head)}.")
            continue
        if len(rows) > MAX_ROWS + 1:
            err(name, 0, "", f"More than {MAX_ROWS} rows.")
            continue
        for i, raw in enumerate(rows[1:], start=2):
            vals = [_cell(v) for v in (*raw, *([None] * len(head)))][:len(head)]
            if all(v in (None, "") for v in vals):
                continue
            rec = dict(zip(head, vals, strict=True))
            col = ""
            try:
                if name == "WorkWeeks":
                    col = "Off days"
                    off = parse_days(str(rec["Off days"] or ""))
                    col = "Half days"
                    half = parse_half_days(str(rec["Half days"] or ""))
                    col = "Effective from"
                    start = _date(rec["Effective from"], "Effective from")
                    col = "Effective to"
                    end = _date(rec["Effective to"], "Effective to") \
                        if rec["Effective to"] not in (None, "") else None
                    col = ""
                    _week(off, half, start, end, "company")
                    res.weeks.append({"row": i, "off_days": off, "half_days": half,
                                      "effective_from": start.isoformat(),
                                      "effective_to": end.isoformat() if end else None})
                elif name == "Exceptions":
                    col = "Date"
                    d = _date(rec["Date"], "Date")
                    col = "Type"
                    t = str(rec["Type"] or "").upper()
                    if t not in cal.EXCEPTION_TYPES:
                        raise CalendarAdminError("Type must be EXTRA_HOLIDAY or WORKING_DAY.")
                    if any(e["date"] == d.isoformat() for e in res.exceptions):
                        col = "Date"
                        raise CalendarAdminError(f"Second exception on {d.isoformat()}.")
                    res.exceptions.append({"row": i, "date": d.isoformat(), "type": t,
                                           "note": rec["Note"] or None})
                else:
                    if not allow_holidays:
                        raise CalendarAdminError("Only an Admin can import holidays.")
                    col = "Date"
                    d = _date(rec["Date"], "Date")
                    col = "Name"
                    if not rec["Name"]:
                        raise CalendarAdminError("Name is required.")
                    col = "Scope"
                    sc = str(rec["Scope"] or "").upper()
                    if sc not in ("FEDERAL", "EMIRATE"):
                        raise CalendarAdminError("Scope must be FEDERAL or EMIRATE.")
                    col = "Emirate"
                    em = _emirate(str(rec["Emirate"])) if rec["Emirate"] else None
                    if (sc == "EMIRATE") != bool(em) or em == "FEDERAL":
                        raise CalendarAdminError("EMIRATE needs an emirate; FEDERAL none.")
                    col = "Status"
                    stt = str(rec["Status"] or "confirmed").lower()
                    if stt not in HOLIDAY_STATUSES:
                        raise CalendarAdminError("Status must be confirmed or provisional.")
                    res.holidays.append({"row": i, "date": d.isoformat(),
                                         "name": str(rec["Name"]), "scope": sc,
                                         "emirate": em, "status": stt})
            except CalendarAdminError as exc:
                err(name, i, col, exc.message)
    if not any(e["sheet"] == "WorkWeeks" for e in res.errors):
        try:
            cal.check_no_overlap(_week(w["off_days"], w["half_days"],
                                       date.fromisoformat(w["effective_from"]),
                                       date.fromisoformat(w["effective_to"])
                                       if w["effective_to"] else None, "company")
                                 for w in res.weeks)
        except cal.CalendarError as exc:
            err("WorkWeeks", 0, "Effective from", str(exc))
    return res


def apply_import(s: Session, client_id: str, res: ImportResult,
                 user_id: str) -> dict[str, Any]:
    """Replace the client's work weeks and exceptions; add new holidays (Admin)."""
    get_client(s, client_id)
    if res.errors:
        raise CalendarAdminError("Fix the errors shown in the preview first.", 422)
    for model in (CompanyWorkweek, CompanyException):
        for row in s.scalars(select(model).where(model.client_id == client_id)).all():
            s.delete(row)
    s.flush()
    for w in res.weeks:
        s.add(CompanyWorkweek(client_id=client_id, off_days=w["off_days"],
                              half_days=w["half_days"],
                              effective_from=date.fromisoformat(w["effective_from"]),
                              effective_to=date.fromisoformat(w["effective_to"])
                              if w["effective_to"] else None))
    for e in res.exceptions:
        s.add(CompanyException(client_id=client_id, date=date.fromisoformat(e["date"]),
                               type=e["type"], note=e["note"]))
    added = skipped = 0
    if res.holidays:
        materialise_seed(s, "holidays", user_id)
    for h in res.holidays:
        d = date.fromisoformat(h["date"])
        exists = s.scalar(select(Holiday).where(
            Holiday.date == d, Holiday.scope == h["scope"],
            Holiday.emirate.is_(None) if h["emirate"] is None
            else Holiday.emirate == h["emirate"]))
        if exists:
            skipped += 1
            continue
        s.add(Holiday(date=d, name=h["name"], scope=h["scope"], emirate=h["emirate"],
                      status=h["status"]))
        added += 1
    s.flush()
    _validate_all(s) if res.holidays else _validate_client(s, client_id)
    summary = {"work_weeks": len(res.weeks), "exceptions": len(res.exceptions),
               "holidays_added": added, "holidays_skipped": skipped}
    _audit(s, user_id, "calendar_import", "client", client_id, summary)
    stale = mark_stale(s, client_ids=None if added else [client_id], user_id=user_id,
                       reason="calendar import")
    return {**summary, "stale": stale}


def half_day_time(v: str) -> time:
    return cal._parse_time(v)
