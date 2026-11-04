"""Working-calendar endpoints (SPEC 3.5, prompt 3.10).

GET    /v1/calendar/resolve?engagement_id|client_id[&emirate]&start&end -> day statuses
GET    /v1/calendar/clients/{client_id}                 -> all layers for the client
POST   /v1/calendar/clients/{client_id}/workweeks       -> company work week (Manager+)
POST   /v1/calendar/clients/{client_id}/exceptions      -> company exception (Manager+)
DELETE /v1/calendar/clients/{client_id}/{kind}/{id}     -> remove a company item (Manager+)
POST   /v1/calendar/emirate-profiles                    -> federal / emirate week (Admin)
POST   /v1/calendar/holidays                            -> holiday (Admin)
PATCH  /v1/calendar/holidays/{id}                       -> provisional <-> confirmed (Admin)
DELETE /v1/calendar/{emirate-profiles|holidays}/{id}    -> remove (Admin)
GET    /v1/calendar/template                            -> blank Excel template
GET    /v1/calendar/clients/{client_id}/export          -> client calendar as Excel
POST   /v1/calendar/clients/{client_id}/import?apply=   -> preview (default) / apply
Every write re-checks overlaps and marks affected JE runs STALE (returned as ``stale``).
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.deps import CurrentUser, DbSession, check_membership, require_roles
from app.core.security import Principal
from app.models import Engagement, EngagementMember
from app.schemas.calendar import EmirateWeekIn, ExceptionIn, HolidayIn, HolidayPatch, WorkWeekIn
from app.services import calendar as cal
from app.services import calendar_admin as adm

router = APIRouter(prefix="/calendar", tags=["calendar"])
EDIT_ROLES = ("Admin", "Partner", "Manager")
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_DAYS = 3 * 366
MAX_UPLOAD = 5 * 1024 * 1024


def _fail(exc: adm.CalendarAdminError | cal.CalendarError) -> HTTPException:
    if isinstance(exc, adm.CalendarAdminError):
        return HTTPException(exc.status_code, exc.message)
    return HTTPException(409, str(exc))


def _client_access(db: Session, user: Principal, client_id: str, *, edit: bool) -> None:
    try:
        adm.get_client(db, client_id)
    except adm.CalendarAdminError as exc:
        raise _fail(exc) from None
    if user.has_any("Admin"):
        return
    if edit and not user.has_any(*EDIT_ROLES):
        raise HTTPException(403, f"This action needs one of these roles: "
                                 f"{', '.join(EDIT_ROLES)}.")
    member = db.scalar(select(EngagementMember.user_id).join(
        Engagement, Engagement.id == EngagementMember.engagement_id).where(
        Engagement.client_id == client_id, EngagementMember.user_id == user.user_id).limit(1))
    if member is None:
        raise HTTPException(403, "You are not on any engagement for this client.")


@router.get("/resolve")
def resolve(db: DbSession, user: CurrentUser, start: date, end: date,
            engagement_id: str | None = None, client_id: str | None = None,
            emirate: str | None = None,
            include_days: bool = True) -> dict[str, Any]:
    if end < start or (end - start).days > MAX_DAYS:
        raise HTTPException(422, "end must be on/after start and within 3 years.")
    if (engagement_id is None) == (client_id is None):
        raise HTTPException(422, "Give exactly one of engagement_id or client_id.")
    if engagement_id is not None:
        check_membership(db, user, engagement_id)
        eng = db.get(Engagement, engagement_id)
        assert eng is not None
        client_id = eng.client_id
    assert client_id is not None
    _client_access(db, user, client_id, edit=False)
    try:
        rc = cal.resolve_client(client_id, adm._emirate(emirate) if emirate else None,
                                start, end, db)
    except (adm.CalendarAdminError, cal.CalendarError) as exc:
        raise _fail(exc) from None
    out: dict[str, Any] = {"client_id": client_id, "emirate": rc.profile.emirate,
                           "timezone": "Asia/Dubai", "hash": rc.hash,
                           "summary": rc.summary()}
    if include_days:
        out["days"] = [d.as_dict() for d in rc.days.values()]
    return out


@router.get("/clients/{client_id}")
def client_layers(client_id: str, db: DbSession, user: CurrentUser) -> dict[str, Any]:
    _client_access(db, user, client_id, edit=False)
    return adm.layers(db, client_id)


@router.post("/clients/{client_id}/workweeks", status_code=201)
def add_workweek(client_id: str, body: WorkWeekIn, db: DbSession,
                 user: CurrentUser) -> dict[str, Any]:
    _client_access(db, user, client_id, edit=True)
    try:
        row, stale = adm.add_company_week(
            db, client_id, off_days=body.off_days, half_days=body.halves(),
            effective_from=body.effective_from, effective_to=body.effective_to,
            user_id=user.user_id)
    except (adm.CalendarAdminError, cal.CalendarError) as exc:
        db.rollback()
        raise _fail(exc) from None
    out = {**adm.week_row(row, "company"), "stale": stale}
    db.commit()
    return out


@router.post("/clients/{client_id}/exceptions", status_code=201)
def add_exception(client_id: str, body: ExceptionIn, db: DbSession,
                  user: CurrentUser) -> dict[str, Any]:
    _client_access(db, user, client_id, edit=True)
    try:
        row, stale = adm.add_exception(db, client_id, day=body.date, type_=body.type,
                                       note=body.note, user_id=user.user_id)
    except adm.CalendarAdminError as exc:
        db.rollback()
        raise _fail(exc) from None
    out = {"id": row.id, "date": row.date.isoformat(), "type": row.type, "note": row.note,
           "stale": stale}
    db.commit()
    return out


@router.delete("/clients/{client_id}/{kind}/{item_id}")
def delete_company(client_id: str, kind: Literal["workweeks", "exceptions"], item_id: int,
                   db: DbSession, user: CurrentUser) -> dict[str, Any]:
    _client_access(db, user, client_id, edit=True)
    try:
        stale = adm.delete_company_item(db, client_id, kind.rstrip("s"), item_id,
                                        user.user_id)
    except adm.CalendarAdminError as exc:
        raise _fail(exc) from None
    db.commit()
    return {"deleted": item_id, "stale": stale}


AdminUser = Annotated[Principal, Depends(require_roles("Admin"))]


@router.post("/emirate-profiles", status_code=201)
def add_emirate_profile(body: EmirateWeekIn, db: DbSession,
                        user: AdminUser) -> dict[str, Any]:
    try:
        row, stale = adm.add_emirate_week(
            db, emirate=body.emirate, off_days=body.off_days, half_days=body.halves(),
            effective_from=body.effective_from, effective_to=body.effective_to,
            user_id=user.user_id)
    except (adm.CalendarAdminError, cal.CalendarError) as exc:
        db.rollback()
        raise _fail(exc) from None
    out = {**adm.week_row(row, "federal" if row.emirate == "FEDERAL" else "emirate"),
           "stale": stale}
    db.commit()
    return out


@router.post("/holidays", status_code=201)
def add_holiday(body: HolidayIn, db: DbSession, user: AdminUser) -> dict[str, Any]:
    try:
        row, stale = adm.add_holiday(db, day=body.date, name=body.name, scope=body.scope,
                                     emirate=body.emirate, status=body.status,
                                     user_id=user.user_id)
    except adm.CalendarAdminError as exc:
        db.rollback()
        raise _fail(exc) from None
    out = {"id": row.id, "date": row.date.isoformat(), "name": row.name, "scope": row.scope,
           "emirate": row.emirate, "status": row.status, "stale": stale}
    db.commit()
    return out


@router.patch("/holidays/{holiday_id}")
def patch_holiday(holiday_id: int, body: HolidayPatch, db: DbSession,
                  user: AdminUser) -> dict[str, Any]:
    try:
        row, stale = adm.update_holiday_status(db, holiday_id, body.status, user.user_id)
    except adm.CalendarAdminError as exc:
        raise _fail(exc) from None
    db.commit()
    return {"id": row.id, "status": row.status, "stale": stale}


@router.delete("/{kind}/{item_id}")
def delete_global(kind: Literal["emirate-profiles", "holidays"], item_id: int,
                  db: DbSession, user: AdminUser) -> dict[str, Any]:
    try:
        stale = adm.delete_global_item(
            db, "emirate_profile" if kind == "emirate-profiles" else "holiday", item_id,
            user.user_id)
    except adm.CalendarAdminError as exc:
        raise _fail(exc) from None
    db.commit()
    return {"deleted": item_id, "stale": stale}


def _xlsx(body: bytes, name: str) -> Response:
    return Response(body, media_type=XLSX,
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/template")
def template(db: DbSession, user: CurrentUser) -> Response:
    return _xlsx(adm.export_workbook(db, None), "calendar_template.xlsx")


@router.get("/clients/{client_id}/export")
def export(client_id: str, db: DbSession, user: CurrentUser) -> Response:
    _client_access(db, user, client_id, edit=False)
    return _xlsx(adm.export_workbook(db, client_id), f"calendar_{client_id[:8]}.xlsx")


@router.post("/clients/{client_id}/import")
async def import_calendar(client_id: str, db: DbSession, user: CurrentUser,
                          file: Annotated[UploadFile, File()],
                          apply: Annotated[bool, Query()] = False) -> dict[str, Any]:
    _client_access(db, user, client_id, edit=True)
    body = await file.read(MAX_UPLOAD + 1)
    if len(body) > MAX_UPLOAD:
        raise HTTPException(413, "Calendar workbooks are limited to 5 MB.")
    try:
        res = adm.parse_workbook(body, allow_holidays=user.has_any("Admin"))
        if not apply or res.errors:
            return {"applied": False, **res.preview()}
        out = adm.apply_import(db, client_id, res, user.user_id)
    except (adm.CalendarAdminError, cal.CalendarError) as exc:
        db.rollback()
        raise _fail(exc) from None
    db.commit()
    return {"applied": True, **res.preview(), **out}
