"""/v1/calendar endpoints (prompt 3.10)."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi.testclient import TestClient

from app.core.db import session_factory
from app.models import Engagement
from app.services import calendar_admin as adm
from tests.conftest import auth
from tests.unit.test_calendar_admin import H, _book, _run, _status

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _cid(engagement: str) -> str:
    with session_factory()() as s:
        eng = s.get(Engagement, engagement)
        assert eng is not None
        return eng.client_id


def test_resolve_access_and_validation(client: TestClient, token: Any,
                                       engagement: str) -> None:
    mgr, staff = auth(token(sub="user-1", roles=["Manager"])), auth(
        token(sub="user-2", roles=["Staff"]))
    outsider = auth(token(sub="x", roles=["Manager"]))
    q = {"engagement_id": engagement, "start": "2025-01-10", "end": "2025-01-11"}
    r = client.get("/v1/calendar/resolve", params=q, headers=staff)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["timezone"] == "Asia/Dubai" and body["emirate"] == "Dubai"
    assert [d["reason"] for d in body["days"]] == ["half_day", "weekend"]
    assert body["days"][0]["half_day_cutoff"] == "12:00"
    assert client.get("/v1/calendar/resolve", params=q, headers=outsider).status_code == 403
    cid = _cid(engagement)
    q2 = {"client_id": cid, "emirate": "sharjah", "start": "2025-01-10", "end": "2025-01-10",
          "include_days": "false"}
    r = client.get("/v1/calendar/resolve", params=q2, headers=mgr)
    assert r.status_code == 200 and r.json()["emirate"] == "Sharjah" and "days" not in r.json()
    assert client.get("/v1/calendar/resolve", params={**q2, "emirate": "Mars"},
                      headers=mgr).status_code == 422
    for bad in ({"start": "2025-02-01", "end": "2025-01-01"},
                {"start": "2020-01-01", "end": "2025-01-01"},
                {"engagement_id": None, "client_id": None}):
        p = {k: v for k, v in {**q, **bad}.items() if v is not None}
        assert client.get("/v1/calendar/resolve", params=p, headers=mgr).status_code == 422
    assert client.get("/v1/calendar/clients/nope", headers=mgr).status_code == 404
    lay = client.get(f"/v1/calendar/clients/{cid}", headers=staff).json()
    assert lay["federal_source"].startswith("seed")
    admin = auth(token(sub="adm", roles=["Admin"]))
    assert client.get(f"/v1/calendar/clients/{cid}", headers=admin).status_code == 200


def test_company_edits_mark_stale(client: TestClient, token: Any, engagement: str) -> None:
    mgr = auth(token(sub="user-1", roles=["Manager"]))
    staff = auth(token(sub="user-2", roles=["Staff"]))
    cid = _cid(engagement)
    run = _run(engagement, date(2025, 1, 1), date(2025, 12, 31))
    url = f"/v1/calendar/clients/{cid}"
    body = {"date": "2025-12-02", "type": "WORKING_DAY", "note": "year-end count"}
    assert client.post(f"{url}/exceptions", json=body, headers=staff).status_code == 403
    r = client.post(f"{url}/exceptions", json=body, headers=mgr)
    assert r.status_code == 201 and r.json()["stale"][0]["id"] == run
    assert _status(run) == "STALE"
    assert client.post(f"{url}/exceptions", json=body, headers=mgr).status_code == 409
    ex_id = r.json()["id"]
    wk = {"off_days": [7], "half_days": {"6": "13:00"}, "effective_from": "2026-01-01"}
    r = client.post(f"{url}/workweeks", json=wk, headers=mgr)
    assert r.status_code == 201 and r.json()["level"] == "company"
    wk_id = r.json()["id"]
    assert client.post(f"{url}/workweeks", json=wk, headers=mgr).status_code == 409
    for bad in ({**wk, "off_days": [8]}, {**wk, "half_days": {"5": "noon"}},
                {**wk, "off_days": [6], "half_days": {"6": "12:00"},
                 "effective_from": "2030-01-01"}):
        assert client.post(f"{url}/workweeks", json=bad, headers=mgr).status_code == 422
    assert client.delete(f"{url}/workweeks/{wk_id}", headers=mgr).status_code == 200
    assert client.delete(f"{url}/exceptions/{ex_id}", headers=mgr).status_code == 200
    assert client.delete(f"{url}/exceptions/{ex_id}", headers=mgr).status_code == 404


def test_admin_layers(client: TestClient, token: Any, engagement: str) -> None:
    admin = auth(token(sub="adm", roles=["Admin"]))
    mgr = auth(token(sub="user-1", roles=["Manager"]))
    hol = {"date": "2025-07-15", "name": "Provisional", "scope": "EMIRATE",
           "emirate": "Dubai", "status": "provisional"}
    assert client.post("/v1/calendar/holidays", json=hol, headers=mgr).status_code == 403
    r = client.post("/v1/calendar/holidays", json=hol, headers=admin)
    assert r.status_code == 201 and r.json()["status"] == "provisional"
    hid = r.json()["id"]
    assert client.post("/v1/calendar/holidays", json=hol, headers=admin).status_code == 409
    r = client.patch(f"/v1/calendar/holidays/{hid}", json={"status": "confirmed"},
                     headers=admin)
    assert r.json()["status"] == "confirmed"
    assert client.patch("/v1/calendar/holidays/999", json={"status": "confirmed"},
                        headers=admin).status_code == 404
    ep = {"emirate": "Sharjah", "off_days": [5, 6, 7], "effective_from": "2025-01-01"}
    r = client.post("/v1/calendar/emirate-profiles", json=ep, headers=admin)
    assert r.status_code == 201 and r.json()["level"] == "emirate"
    assert client.post("/v1/calendar/emirate-profiles", json=ep,
                       headers=admin).status_code == 409
    fed = {**ep, "emirate": "FEDERAL", "off_days": [6, 7], "effective_from": "2030-01-01"}
    assert client.post("/v1/calendar/emirate-profiles", json=fed,
                       headers=admin).status_code == 409  # overlaps the copied seed week
    assert client.delete(f"/v1/calendar/emirate-profiles/{r.json()['id']}",
                         headers=admin).status_code == 200
    assert client.delete(f"/v1/calendar/holidays/{hid}", headers=admin).status_code == 200
    assert client.delete("/v1/calendar/holidays/999", headers=admin).status_code == 404


def test_excel_template_preview_apply(client: TestClient, token: Any, engagement: str) -> None:
    mgr = auth(token(sub="user-1", roles=["Manager"]))
    cid = _cid(engagement)
    r = client.get("/v1/calendar/template", headers=mgr)
    assert r.status_code == 200 and r.headers["content-type"] == XLSX
    files = {"file": ("cal.xlsx", r.content, XLSX)}
    url = f"/v1/calendar/clients/{cid}/import"
    p = client.post(url, files=files, headers=mgr).json()
    assert p["applied"] is False and p["ok"] is True and p["counts"]["work_weeks"] == 1
    a = client.post(url, params={"apply": "true"}, files=files, headers=mgr).json()
    assert a["applied"] is True and a["work_weeks"] == 1
    exp = client.get(f"/v1/calendar/clients/{cid}/export", headers=mgr)
    assert exp.status_code == 200 and "attachment" in exp.headers["content-disposition"]
    bad = _book({"WorkWeeks": [H["WorkWeeks"]], "Exceptions": [H["Exceptions"]],
                 "Holidays": [H["Holidays"], ["2025-07-15", "Day", "FEDERAL", None, None]]})
    r = client.post(url, params={"apply": "true"}, headers=mgr,
                    files={"file": ("c.xlsx", bad, XLSX)}).json()
    assert r["applied"] is False and r["errors"][0]["message"].startswith("Only an Admin")
    assert client.post(url, headers=mgr, files={"file": ("c.xlsx", b"junk", XLSX)}
                       ).status_code == 422
    big = b"0" * (5 * 1024 * 1024 + 1)
    assert client.post(url, headers=mgr, files={"file": ("c.xlsx", big, XLSX)}
                       ).status_code == 413
    assert adm.IMPLEMENTED_BY_PROMPT == "3.10"
