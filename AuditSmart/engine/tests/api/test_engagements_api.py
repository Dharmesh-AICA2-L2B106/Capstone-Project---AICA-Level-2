"""Stage 5.2 engagement sync (D50-D55): PUT/GET /v1/engagements/{id}."""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.api.test_sampling_api import DUMMY, _body, _dataset
from tests.conftest import auth

ENG = "11111111-1111-4111-8111-111111111111"
CLIENT = "22222222-2222-4222-8222-222222222222"
ENG_B = "33333333-3333-4333-8333-333333333333"
CLIENT_B = "44444444-4444-4444-8444-444444444444"


def _db() -> Any:
    from app.core.db import session_factory

    return session_factory()()


def _audit(action: str) -> list[Any]:
    from app.models import AuditLog

    with _db() as s:
        return list(s.scalars(select(AuditLog).where(AuditLog.action == action)))


def payload(**kw: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "client": {"id": CLIENT, "client_code": "C001", "name": "Dummy Trading LLC",
                   "emirate": "Dubai", "entity_type": "LLC"},
        "fye": "2025-12-31", "framework": "IFRS", "materiality": "1500000.00",
        "perf_materiality": "1125000", "trivial": 75000, "status": "planning",
        "members": [{"user_id": "a-mgr", "role": "Manager"},
                    {"user_id": "a-senior", "role": "Senior"}]}
    body.update(kw)
    return body


@pytest.fixture
def ctx(client: TestClient, token: Callable[..., str]) -> dict[str, Any]:
    admin = token(sub="platform", roles=["Admin"])
    for fid in ("firm-a", "firm-b"):
        r = client.post("/v1/firms", headers=auth(admin), json={"id": fid, "name": fid.upper()})
        assert r.status_code == 201, r.text

    def tok(firm: str | None, sub: str, *roles: str) -> str:
        return token(sub=sub, roles=list(roles), extra={"firm_id": firm} if firm else None)

    return {"admin": admin,
            "a_mgr": tok("firm-a", "a-mgr", "Manager"),
            "a_senior": tok("firm-a", "a-senior", "Senior"),
            "a_p": tok("firm-a", "a-p", "Partner"),
            "a_tp": tok("firm-a", "a-tp", "TaxPartner"),
            "a_admin": tok("firm-a", "a-admin", "Admin"),
            "a_mgr2": tok("firm-a", "a-mgr2", "Manager"),
            "b_mgr": tok("firm-b", "b-mgr", "Manager"),
            "b_admin": tok("firm-b", "b-admin", "Admin"),
            "ghost": tok("ghost", "g", "Manager"),
            "nofirm": tok(None, "n", "Manager")}


def _put(tc: TestClient, tok: str, eng: str = ENG, **kw: Any) -> Any:
    return tc.put(f"/v1/engagements/{eng}", headers=auth(tok), json=payload(**kw))


def test_create_then_update_idempotent(client: TestClient, ctx: dict[str, Any]) -> None:
    r = _put(client, ctx["a_mgr"])
    assert r.status_code == 201, r.text
    b = r.json()
    assert b["created"] is True and b["stale"] == []
    assert b["engagement"] == {"id": ENG, "client_id": CLIENT, "fye": "2025-12-31",
                               "framework": "IFRS", "materiality": "1500000.00",
                               "perf_materiality": "1125000.00", "trivial": "75000.00",
                               "status": "planning"}
    assert b["client"] == {"id": CLIENT, "client_code": "C001", "name": "Dummy Trading LLC",
                           "emirate": "Dubai", "entity_type": "LLC", "firm_id": "firm-a"}
    assert b["members"] == [{"user_id": "a-mgr", "role": "Manager"},
                            {"user_id": "a-senior", "role": "Senior"}]
    again = _put(client, ctx["a_mgr"])
    assert again.status_code == 200 and again.json()["created"] is False
    assert len(_audit("engagement_sync_create")) == 1
    assert _audit("engagement_sync_update") == []  # no change -> no audit row
    # update: materiality, emirate code, team replaced, role alias normalised
    r = _put(client, ctx["a_mgr"], materiality="2000000.5",
             client={**payload()["client"], "emirate": "shj", "name": "Renamed LLC"},
             members=[{"user_id": "a-mgr", "role": "manager"},
                      {"user_id": "a-tp", "role": "tax_partner"}])
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["engagement"]["materiality"] == "2000000.50"
    assert b["client"]["emirate"] == "Sharjah" and b["client"]["name"] == "Renamed LLC"
    assert b["members"] == [{"user_id": "a-mgr", "role": "Manager"},
                            {"user_id": "a-tp", "role": "TaxPartner"}]
    upd = _audit("engagement_sync_update")
    assert len(upd) == 1 and upd[0].old["materiality"] == "1500000.00"
    assert upd[0].new["materiality"] == "2000000.50" and upd[0].new["firm_id"] == "firm-a"
    assert {m["user_id"] for m in upd[0].old["members"]} == {"a-mgr", "a-senior"}
    assert len(_audit("client_sync_create")) == 1 and len(_audit("client_sync_update")) == 1
    # omitted optional fields keep their value; explicit null clears
    body = payload()
    for k in ("framework", "materiality", "perf_materiality", "trivial", "status"):
        body.pop(k)
    r = client.put(f"/v1/engagements/{ENG}", headers=auth(ctx["a_mgr"]), json=body)
    assert r.json()["engagement"]["materiality"] == "2000000.50"
    assert r.json()["engagement"]["framework"] == "IFRS"
    r = _put(client, ctx["a_mgr"], framework=None, status="Fieldwork")
    assert r.json()["engagement"]["framework"] is None
    assert r.json()["engagement"]["status"] == "fieldwork"
    g = client.get(f"/v1/engagements/{ENG}", headers=auth(ctx["a_senior"]))
    assert g.status_code == 200 and g.json()["created"] is None


def test_roles_and_firm_claim(client: TestClient, ctx: dict[str, Any]) -> None:
    assert _put(client, ctx["a_senior"]).status_code == 403  # app role Senior
    r = _put(client, ctx["nofirm"])
    assert r.status_code == 403 and "not linked to a firm" in r.json()["detail"]
    r = _put(client, ctx["ghost"])
    assert r.status_code == 403 and "not registered" in r.json()["detail"]
    assert client.put(f"/v1/engagements/{ENG}", json=payload()).status_code == 401
    assert _put(client, ctx["a_admin"]).status_code == 201  # firm Admin may create
    # update needs membership as Manager/Partner/TaxPartner, or firm Admin
    r = _put(client, ctx["a_mgr2"])
    assert r.status_code == 403 and "not a member" in r.json()["detail"]
    assert _put(client, ctx["a_p"]).status_code == 403
    assert _put(client, ctx["a_mgr"]).status_code == 200
    assert _put(client, ctx["a_admin"], status="review").status_code == 200
    # a member Senior (app role Manager would pass role check) cannot edit
    _put(client, ctx["a_mgr"], members=[{"user_id": "a-mgr", "role": "Manager"},
                                        {"user_id": "a-mgr2", "role": "Senior"}])
    r = _put(client, ctx["a_mgr2"])
    assert r.status_code == 403 and "(Senior)" in r.json()["detail"]
    assert client.get(f"/v1/engagements/{ENG}", headers=auth(ctx["a_mgr2"])).status_code == 200
    assert client.get(f"/v1/engagements/{ENG}", headers=auth(ctx["a_p"])).status_code == 403
    assert client.get(f"/v1/engagements/{ENG}", headers=auth(ctx["a_admin"])).status_code == 200
    assert client.get("/v1/engagements/nope", headers=auth(ctx["a_mgr"])).status_code == 404


def test_cross_firm(client: TestClient, ctx: dict[str, Any]) -> None:
    assert _put(client, ctx["a_mgr"]).status_code == 201
    r = _put(client, ctx["b_admin"])  # firm B targets firm A's engagement
    assert r.status_code == 403 and r.json()["detail"] == "This engagement belongs to another firm."
    r = client.get(f"/v1/engagements/{ENG}", headers=auth(ctx["b_admin"]))
    assert r.status_code == 403
    # firm B tries to attach a new engagement to firm A's client -> 404, nothing created
    r = _put(client, ctx["b_mgr"], eng=ENG_B,
             members=[{"user_id": "b-mgr", "role": "Manager"}])
    assert r.status_code == 404 and r.json()["detail"] == "Client not found"
    assert client.get(f"/v1/engagements/{ENG_B}", headers=auth(ctx["b_mgr"])).status_code == 404
    # same client code in another firm is fine (D52); duplicate inside a firm is 409
    r = _put(client, ctx["b_mgr"], eng=ENG_B,
             client={**payload()["client"], "id": CLIENT_B},
             members=[{"user_id": "b-mgr", "role": "Manager"}])
    assert r.status_code == 201, r.text
    r = _put(client, ctx["a_mgr"], eng=ENG_B.replace("3", "5"),
             client={**payload()["client"], "id": CLIENT_B.replace("4", "6")})
    assert r.status_code == 409 and "already used" in r.json()["detail"]
    # an engagement cannot move to another client
    r = _put(client, ctx["a_mgr"], client={**payload()["client"], "id": CLIENT_B.replace("4", "7"),
                                          "client_code": "C002"})
    assert r.status_code == 409 and "another client" in r.json()["detail"]
    assert client.get(f"/v1/engagements/{ENG}", headers=auth(ctx["a_mgr"])).json()[
        "client"]["client_code"] == "C001"


def test_unassigned_client_and_engagement(client: TestClient, ctx: dict[str, Any],
                                          engagement: str) -> None:
    from app.models import Engagement

    with _db() as s:
        legacy_client = s.get(Engagement, engagement).client_id
    r = _put(client, ctx["a_mgr"], eng=ENG,
             client={**payload()["client"], "id": legacy_client})
    assert r.status_code == 409 and "platform administrator" in r.json()["detail"]
    r = _put(client, ctx["a_admin"], eng=engagement)
    assert r.status_code == 409 and "not linked to a firm" in r.json()["detail"]
    assert client.put(f"/v1/firms/firm-a/clients/{legacy_client}",
                      headers=auth(ctx["admin"])).status_code == 200
    r = _put(client, ctx["a_admin"], eng=engagement,
             client={**payload()["client"], "id": legacy_client, "client_code": "DUMMY01"})
    assert r.status_code == 200, r.text


@pytest.mark.parametrize("change", [
    {"materiality": "12.345"}, {"materiality": "-1"}, {"materiality": "abc"},
    {"perf_materiality": "2000000", "materiality": "1000000"},
    {"trivial": "2000000", "materiality": "1000000", "perf_materiality": None},
    {"members": []}, {"members": [{"user_id": "x", "role": "Senior"}]},
    {"members": [{"user_id": "a-mgr", "role": "Manager"}, {"user_id": "a-mgr", "role": "Staff"}]},
    {"members": [{"user_id": "a-mgr", "role": "Boss"}]},
    {"client": {"id": CLIENT, "client_code": "C1", "name": "X", "emirate": "Mars"}},
    {"client": {"id": "bad id!", "client_code": "C1", "name": "X", "emirate": "Dubai"}},
    {"fye": "2025-13-01"}, {"unexpected": 1},
])
def test_validation(client: TestClient, ctx: dict[str, Any], change: dict[str, Any]) -> None:
    r = _put(client, ctx["a_mgr"], **change)
    assert r.status_code == 422, r.text


def test_bad_path_id(client: TestClient, ctx: dict[str, Any]) -> None:
    r = client.put("/v1/engagements/bad%20id", headers=auth(ctx["a_mgr"]), json=payload())
    assert r.status_code == 422


def test_membership_drives_engine_access_and_fye_stale(client: TestClient,
                                                       ctx: dict[str, Any]) -> None:
    assert _put(client, ctx["a_mgr"]).status_code == 201
    did = _dataset(client, ctx["a_senior"], ENG, DUMMY)  # synced Senior may upload
    r = client.post("/v1/sample", headers=auth(ctx["a_mgr"]), json=_body(did))
    assert r.status_code == 201, r.text
    assert r.json()["n_required"] == 161 and r.json()["cf_value"] == "3.00"
    sid = r.json()["sample_id"] if "sample_id" in r.json() else r.json()["id"]
    # firm B cannot upload into firm A's engagement
    r = client.post("/v1/datasets", headers=auth(ctx["b_mgr"]), data={"engagement_id": ENG},
                    files={"file": ("gl.csv", DUMMY)})
    assert r.status_code == 403
    # remove the Senior -> no more access
    team = [{"user_id": "a-mgr", "role": "Manager"}]
    assert _put(client, ctx["a_mgr"], members=team).status_code == 200
    r = client.post("/v1/datasets", headers=auth(ctx["a_senior"]), data={"engagement_id": ENG},
                    files={"file": ("gl.csv", DUMMY)})
    assert r.status_code == 403 and "not a member" in r.json()["detail"]
    # materiality-only change: results stay current
    r = _put(client, ctx["a_mgr"], members=team, materiality="1600000")
    assert r.json()["stale"] == []
    # year-end change: current results become STALE (audit-logged)
    r = _put(client, ctx["a_mgr"], members=team, fye="2025-06-30")
    assert r.status_code == 200
    stale = r.json()["stale"]
    assert [x["kind"] for x in stale] == ["sample"] and stale[0]["id"] == sid
    from app.models import Sample

    with _db() as s:
        assert s.get(Sample, sid).status == "STALE"
    assert any("year end changed" in a.new["reason"] for a in _audit("stale"))
    assert _put(client, ctx["a_mgr"], members=team, fye="2025-06-30").json()["stale"] == []


def test_emirate_change_rechecks_je_calendar(client: TestClient, ctx: dict[str, Any]) -> None:
    assert _put(client, ctx["a_mgr"]).status_code == 201
    did = _dataset(client, ctx["a_mgr"], ENG, DUMMY)
    r = client.post("/v1/je-tests", headers=auth(ctx["a_mgr"]), json={"dataset_id": did})
    assert r.status_code == 202, r.text
    run = r.json()["je_run_id"]
    from datetime import date

    from app.models import EmirateProfile, JeRun

    with _db() as s:  # Abu Dhabi gets its own (different) work week
        s.add(EmirateProfile(emirate="Abu Dhabi", off_days=[5], half_days=None,
                             effective_from=date(2020, 1, 1), effective_to=None))
        s.commit()
    body = copy.deepcopy(payload())
    body["client"]["emirate"] = "Abu Dhabi"
    r = client.put(f"/v1/engagements/{ENG}", headers=auth(ctx["a_mgr"]), json=body)
    assert r.status_code == 200
    assert r.json()["stale"] == [{"kind": "je_run", "id": run, "engagement_id": ENG}]
    with _db() as s:
        assert s.get(JeRun, run).status == "STALE"


def test_member_role_change_in_place(client: TestClient, ctx: dict[str, Any]) -> None:
    assert _put(client, ctx["a_mgr"]).status_code == 201
    r = _put(client, ctx["a_mgr"], members=[{"user_id": "a-mgr", "role": "Manager"},
                                             {"user_id": "a-senior", "role": "staff"}])
    assert r.status_code == 200, r.text
    assert {m["user_id"]: m["role"] for m in r.json()["members"]} == {
        "a-mgr": "Manager", "a-senior": "Staff"}
