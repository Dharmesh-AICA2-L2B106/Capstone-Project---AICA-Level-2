"""FTA rules monitor endpoints (SPEC 3.4, prompt 3.9).  Admin / Tax Partner only.

GET   /v1/rules-monitor/sources              -> watched sources
POST  /v1/rules-monitor/sources              -> add a source (https or urn: placeholder)
PATCH /v1/rules-monitor/sources/{id}         -> edit name / url / type / active
POST  /v1/rules-monitor/check                -> check-now (background job; ?force=)
POST  /v1/rules-monitor/upload               -> manual PDF/HTML/text upload -> proposals
GET   /v1/rules-monitor/alerts               -> update alerts (filter status / kind)
POST  /v1/rules-monitor/alerts/{id}/close    -> close an alert
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select

from app.api.v1.deps import CurrentUser, DbSession, require_roles
from app.core.db import session_factory
from app.models import UpdateAlert, WatchedSource
from app.schemas.rules_monitor import SourceIn, SourcePatch
from app.services import jobs
from app.services import rules_monitor as svc

ADMIN_ROLES = ("Admin", "TaxPartner")
router = APIRouter(prefix="/rules-monitor", tags=["rules-monitor"],
                   dependencies=[Depends(require_roles(*ADMIN_ROLES))])


def get_fetcher() -> svc.Fetcher:
    return svc.PoliteFetcher()


def get_extractor() -> svc.Extractor | None:
    return None  # -> configured AI provider at call time


def get_notifier() -> svc.Notifier:
    return svc.log_notifier


Fetch = Annotated[svc.Fetcher, Depends(get_fetcher)]
Extract = Annotated[svc.Extractor | None, Depends(get_extractor)]
Notify = Annotated[svc.Notifier, Depends(get_notifier)]


def _src(s: WatchedSource) -> dict[str, Any]:
    return {"id": s.id, "name": s.name, "url": s.url, "type": s.type, "active": s.active,
            "last_hash": s.last_hash, "last_checked": s.last_checked,
            "last_error": s.last_error, "due": svc.due(s)}


def _alert(a: UpdateAlert) -> dict[str, Any]:
    return {"id": a.id, "source_id": a.source_id, "kind": a.kind, "status": a.status,
            "detected_at": a.detected_at, "summary": a.summary,
            "proposal_ids": a.proposal_ids or [], "details": a.details or {}}


@router.get("/sources")
def list_sources(db: DbSession) -> list[dict[str, Any]]:
    return [_src(s) for s in db.scalars(select(WatchedSource).order_by(WatchedSource.url))]


@router.post("/sources", status_code=201)
def add_source(body: SourceIn, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    if db.scalar(select(WatchedSource).where(WatchedSource.url == body.url)):
        raise HTTPException(409, "That URL is already watched.")
    s = WatchedSource(url=body.url, name=body.name, type=body.type,
                      active=body.active and body.url.startswith("https://"))
    db.add(s)
    db.commit()
    return _src(s)


@router.patch("/sources/{source_id}")
def edit_source(source_id: str, body: SourcePatch, user: CurrentUser,
                db: DbSession) -> dict[str, Any]:
    s = db.get(WatchedSource, source_id)
    if s is None:
        raise HTTPException(404, "Watched source not found.")
    data = body.model_dump(exclude_unset=True)
    if "url" in data and data["url"] != s.url:
        if db.scalar(select(WatchedSource).where(WatchedSource.url == data["url"])):
            raise HTTPException(409, "That URL is already watched.")
        s.last_hash, s.last_links = None, None  # new document -> fresh baseline
    for k, v in data.items():
        setattr(s, k, v)
    if s.active and not s.url.startswith("https://"):
        raise HTTPException(422, "Only https:// sources can be active; record the URL first.")
    db.commit()
    return _src(s)


@router.post("/check", status_code=202)
def check_now(user: CurrentUser, fetcher: Fetch, extractor: Extract, notify: Notify,
              force: bool = True) -> dict[str, str]:
    def run(job_id: str) -> str:
        with session_factory()() as s:
            res = svc.check_all(s, fetcher, force=force, extractor=extractor, notify=notify)
            s.commit()
        return f"checked={res['checked']};alerts={','.join(res['alerts'])}"
    return {"job_id": jobs.submit("rules_monitor", run, created_by=user.user_id)}


@router.post("/upload", status_code=201)
def upload(user: CurrentUser, db: DbSession, extractor: Extract, notify: Notify,
           file: Annotated[UploadFile, File()],
           source_url: Annotated[str | None, Form()] = None) -> dict[str, Any]:
    body = file.file.read(svc.MAX_BYTES + 1)
    try:
        a = svc.upload(db, body, file_name=file.filename or "upload", source_url=source_url,
                       uploaded_by=user.user_id, extractor=extractor, notify=notify)
    except svc.MonitorError as exc:
        db.rollback()
        raise HTTPException(exc.status_code, exc.message) from None
    db.commit()
    return _alert(a)


@router.get("/alerts")
def list_alerts(db: DbSession, status: str | None = None,
                kind: str | None = None) -> list[dict[str, Any]]:
    q = select(UpdateAlert).order_by(UpdateAlert.detected_at.desc())
    if status:
        q = q.where(UpdateAlert.status == status)
    if kind:
        q = q.where(UpdateAlert.kind == kind)
    return [_alert(a) for a in db.scalars(q)]


@router.post("/alerts/{alert_id}/close")
def close_alert(alert_id: str, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    a = db.get(UpdateAlert, alert_id)
    if a is None:
        raise HTTPException(404, "Alert not found.")
    a.status = "closed"
    db.commit()
    return _alert(a)
